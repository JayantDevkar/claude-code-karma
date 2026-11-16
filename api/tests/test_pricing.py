"""Model pricing: shipped JSON defaults plus the user's override file."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import Settings, settings
from models.usage import TokenUsage, load_pricing

DEFAULTS = Path(__file__).parent.parent / "models" / "pricing.json"


def _override(tmp_path: Path, data) -> Path:
    path = tmp_path / "pricing.json"
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
    return path


def test_sonnet_5_5_cache_read_bills_at_ten_cents_per_million():
    usage = TokenUsage(cache_read_input_tokens=1_000_000)
    assert usage.calculate_cost("claude-sonnet-5-5") == pytest.approx(0.10)


def test_override_replaces_one_model_and_adds_new(tmp_path):
    override = _override(
        tmp_path,
        {
            "models": {
                "claude-opus-5-5": {"input": 1.0, "output": 2.0},
                "claude-new-9": {"input": 3.0, "output": 4.0},
            }
        },
    )
    defaults = load_pricing(DEFAULTS, None)
    pricing = load_pricing(DEFAULTS, override)

    assert pricing["models"]["claude-opus-5-5"] == {"input": 1.0, "output": 2.0}
    assert pricing["models"]["claude-new-9"] == {"input": 3.0, "output": 4.0}
    assert pricing["models"]["claude-sonnet-4-6"] == defaults["models"]["claude-sonnet-4-6"]


def test_override_multiplier_replaces_only_that_key(tmp_path):
    override = _override(tmp_path, {"multipliers": {"cache_read": 0.2}})
    pricing = load_pricing(DEFAULTS, override)
    assert pricing["multipliers"] == {
        "cache_write_5m": 1.25,
        "cache_write_1h": 2.0,
        "cache_read": 0.2,
    }


def test_unparseable_override_falls_back_to_defaults(tmp_path):
    override = _override(tmp_path, "{not json")
    assert load_pricing(DEFAULTS, override) == load_pricing(DEFAULTS, None)


def test_invalid_override_entry_is_skipped(tmp_path):
    override = _override(
        tmp_path,
        {
            "models": {
                "claude-a-1": {"input": "x", "output": 1},
                "claude-b-1": {"input": 1, "output": 2},
            }
        },
    )
    models = load_pricing(DEFAULTS, override)["models"]
    assert "claude-a-1" not in models
    assert models["claude-b-1"] == {"input": 1, "output": 2}


def test_unknown_default_model_override_is_ignored(tmp_path):
    override = _override(tmp_path, {"default_model": "claude-nope"})
    assert load_pricing(DEFAULTS, override)["default_model"] == "claude-sonnet-4-6"


def test_missing_override_file_uses_defaults(tmp_path):
    absent = tmp_path / "absent.json"
    assert load_pricing(DEFAULTS, absent) == load_pricing(DEFAULTS, None)


def test_models_section_that_is_not_an_object_is_skipped(tmp_path, caplog):
    override = _override(tmp_path, {"models": [{"input": 1}], "multipliers": {"cache_read": 0.2}})
    pricing = load_pricing(DEFAULTS, override)
    assert pricing["models"] == load_pricing(DEFAULTS, None)["models"]
    assert pricing["multipliers"]["cache_read"] == 0.2
    assert "models" in caplog.text


def test_multipliers_section_that_is_not_an_object_is_skipped(tmp_path, caplog):
    override = _override(
        tmp_path, {"multipliers": 0.2, "models": {"claude-b-1": {"input": 1, "output": 2}}}
    )
    pricing = load_pricing(DEFAULTS, override)
    assert pricing["multipliers"] == load_pricing(DEFAULTS, None)["multipliers"]
    assert pricing["models"]["claude-b-1"] == {"input": 1, "output": 2}
    assert "multipliers" in caplog.text


def test_default_model_that_is_not_a_string_is_ignored(tmp_path, caplog):
    override = _override(tmp_path, {"default_model": ["x"], "multipliers": {"cache_read": 0.2}})
    pricing = load_pricing(DEFAULTS, override)
    assert pricing["default_model"] == load_pricing(DEFAULTS, None)["default_model"]
    assert pricing["multipliers"]["cache_read"] == 0.2
    assert "default_model" in caplog.text


@pytest.mark.parametrize(
    "bad",
    ["NaN", "Infinity", "-Infinity", "1e999", "-1", pytest.param("1" + "0" * 400, id="huge-int")],
)
def test_non_finite_or_negative_price_is_skipped(tmp_path, bad):
    override = _override(
        tmp_path,
        '{"models": {"claude-a-1": {"input": %s, "output": 1},'
        ' "claude-b-1": {"input": 1, "output": 2, "cache_read": %s}}}' % (bad, bad),
    )
    models = load_pricing(DEFAULTS, override)["models"]
    assert "claude-a-1" not in models
    assert "claude-b-1" not in models


def test_bad_price_does_not_drop_a_valid_neighbour(tmp_path):
    override = _override(
        tmp_path,
        '{"models": {"claude-a-1": {"input": NaN, "output": 1},'
        ' "claude-b-1": {"input": 1, "output": 2}}}',
    )
    models = load_pricing(DEFAULTS, override)["models"]
    assert "claude-a-1" not in models
    assert models["claude-b-1"] == {"input": 1, "output": 2}


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-0.5"])
def test_non_finite_or_negative_multiplier_is_skipped(tmp_path, bad):
    override = _override(
        tmp_path, '{"multipliers": {"cache_read": %s, "cache_write_1h": 3.0}}' % bad
    )
    expected = load_pricing(DEFAULTS, None)["multipliers"]
    multipliers = load_pricing(DEFAULTS, override)["multipliers"]
    assert multipliers["cache_read"] == expected["cache_read"]
    assert multipliers["cache_write_1h"] == 3.0


def test_suite_never_reads_the_real_pricing_override():
    assert not settings.pricing_override_path.is_relative_to(Path.home() / ".claude_karma")


def test_pricing_override_path_honours_the_environment(tmp_path, monkeypatch):
    target = tmp_path / "elsewhere.json"
    monkeypatch.setenv("CLAUDE_KARMA_PRICING_OVERRIDE_PATH", str(target))
    assert Settings().pricing_override_path == target


def test_models_usage_loads_the_override_from_the_env_path(tmp_path):
    override = _override(tmp_path, {"models": {"claude-env-9": {"input": 1, "output": 2}}})
    code = "from models.usage import MODEL_PRICING; print('claude-env-9' in MODEL_PRICING)"
    env = {**os.environ, "CLAUDE_KARMA_PRICING_OVERRIDE_PATH": str(override)}
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).parent.parent,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == "True", result.stderr
