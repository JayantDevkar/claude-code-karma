"""Model pricing: shipped JSON defaults plus the user's override file."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

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
