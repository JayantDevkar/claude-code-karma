#!/usr/bin/env python3
"""
Detects drift between karma's vendored Claude Code settings snapshots and the
live upstream sources. Used by .github/workflows/schema-drift.yml — not meant
to be run standalone against real files outside that workflow's temp dir, but
safe to run locally against any pair of schema/reference files for testing.

Two kinds of drift get different treatment:

  - "watched" drift: a settings.json key karma's settings page actually reads
    or writes (schema/watched-keys.json) changed shape, enum, or default, or
    disappeared from the schema entirely. High priority: it can mean karma's
    UI shows a stale default, offers a value Claude Code no longer accepts,
    or silently no-ops -- the exact "spellcheck was on but did nothing"
    failure that motivated this feature. -> a `schema-drift` issue.

  - everything else that changed in either source -> a low-priority
    `schema-drift-digest` issue (also a feed of "new setting to expose"
    ideas for a future settings-page pass).

Prints `key=value` GitHub Actions output lines to stdout; the workflow
redirects them into $GITHUB_OUTPUT. Writes issue body markdown files into
the given output directory when there's something to report.
"""

import argparse
import difflib
import json
from pathlib import Path

# The real vendored schema has 150+ top-level properties. Anything drastically
# smaller is a sign of a bad fetch (a WAF interstitial that happens to be
# valid JSON, a truncated response, an API error body) rather than a real
# schema -- and per-key drift comparison can't tell the difference, since
# from its point of view every watched key just looks "removed". Without this
# check, a bad fetch would both fire a false schema-drift issue for every
# watched key AND open a PR proposing the garbage as the new vendored
# baseline, silently degrading api/routers/settings.py's live validator if
# that PR is merged without close scrutiny.
MIN_EXPECTED_SCHEMA_PROPERTIES = 50


def sanity_check_schema(schema: dict, source: str) -> None:
    """Raise if `schema` doesn't look like a real Claude Code settings schema.

    Called on both the vendored and freshly-fetched schema before either is
    trusted for diffing or as a snapshot-overwrite candidate.
    """
    properties = schema.get("properties")
    count = len(properties) if isinstance(properties, dict) else 0
    if count < MIN_EXPECTED_SCHEMA_PROPERTIES:
        raise ValueError(
            f"{source} schema has only {count} top-level properties (expected at "
            f"least {MIN_EXPECTED_SCHEMA_PROPERTIES}). This looks like a bad fetch, "
            "not a real settings schema -- refusing to treat it as ground truth."
        )


def load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_lines(path: Path) -> list:
    with open(path, "r", encoding="utf-8") as f:
        return f.readlines()


def diff_watched_keys(old_schema: dict, new_schema: dict, watched_keys: list) -> list:
    old_props = old_schema.get("properties", {})
    new_props = new_schema.get("properties", {})
    drift = []
    for key in watched_keys:
        old_val = old_props.get(key)
        new_val = new_props.get(key)
        if old_val != new_val:
            drift.append({"key": key, "old": old_val, "new": new_val})
    return drift


def render_watched_body(drift: list) -> str:
    lines = [
        "Karma's vendored Claude Code settings schema snapshot changed shape "
        "for a key the settings page actually reads or writes.",
        "",
        "For each key below, check `frontend/src/lib/settings-manifest.ts` (or "
        "the hand-written render in `frontend/src/routes/settings/+page.svelte` "
        "for a bespoke section) and the typed Pydantic fields in "
        "`api/routers/settings.py`.",
        "",
    ]
    for entry in drift:
        lines.append(f"## `{entry['key']}`")
        lines.append("")
        if entry["new"] is None:
            lines.append(
                "**No longer in the vendored schema.** This can mean the key was "
                "removed upstream, or -- as happened with `spellcheck` when this "
                "feature was first built -- the community schema simply hasn't "
                "caught up yet. Check the official settings reference before "
                "assuming removal. Previous definition:"
            )
            lines.append("```json")
            lines.append(json.dumps(entry["old"], indent=2))
            lines.append("```")
        elif entry["old"] is None:
            lines.append(
                "**Newly appeared in the schema** (was previously unknown to it). Now:"
            )
            lines.append("```json")
            lines.append(json.dumps(entry["new"], indent=2))
            lines.append("```")
        else:
            lines.append("Old:")
            lines.append("```json")
            lines.append(json.dumps(entry["old"], indent=2))
            lines.append("```")
            lines.append("")
            lines.append("New:")
            lines.append("```json")
            lines.append(json.dumps(entry["new"], indent=2))
            lines.append("```")
        lines.append("")
    return "\n".join(lines)


def render_digest_body(schema_diff: str, reference_diff: str) -> str:
    lines = [
        "Changes in the upstream Claude Code settings schema and/or settings "
        "reference doc, outside the keys karma's settings page currently "
        "watches. Low priority -- mostly useful as a feed of settings karma "
        "could expose next.",
        "",
    ]
    if schema_diff.strip():
        lines += ["## Schema diff", "", "```diff", schema_diff.rstrip("\n"), "```", ""]
    if reference_diff.strip():
        lines += [
            "## Settings reference diff",
            "",
            "```diff",
            reference_diff.rstrip("\n"),
            "```",
            "",
        ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("old_schema", type=Path)
    parser.add_argument("new_schema", type=Path)
    parser.add_argument("old_reference", type=Path)
    parser.add_argument("new_reference", type=Path)
    parser.add_argument("watched_keys", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()

    old_schema = load_json(args.old_schema)
    new_schema = load_json(args.new_schema)
    watched_keys = load_json(args.watched_keys)["keys"]

    # Fail loudly (non-zero exit) before trusting either schema for anything.
    # A GitHub Actions `run:` step failure halts the job here, so a bad fetch
    # can't reach the later issue-creation or snapshot-overwrite steps, which
    # are gated on this step's outputs.
    sanity_check_schema(old_schema, "vendored")
    sanity_check_schema(new_schema, "live")

    watched_drift = diff_watched_keys(old_schema, new_schema, watched_keys)

    schema_diff = "".join(
        difflib.unified_diff(
            load_lines(args.old_schema),
            load_lines(args.new_schema),
            fromfile="vendored schema",
            tofile="live schema",
        )
    )
    reference_diff = "".join(
        difflib.unified_diff(
            load_lines(args.old_reference),
            load_lines(args.new_reference),
            fromfile="vendored reference",
            tofile="live reference",
        )
    )

    has_watched_drift = bool(watched_drift)
    has_digest_drift = bool(schema_diff.strip() or reference_diff.strip())

    args.output_dir.mkdir(parents=True, exist_ok=True)
    if has_watched_drift:
        (args.output_dir / "watched-drift-body.md").write_text(
            render_watched_body(watched_drift), encoding="utf-8"
        )
    if has_digest_drift:
        (args.output_dir / "digest-body.md").write_text(
            render_digest_body(schema_diff, reference_diff), encoding="utf-8"
        )

    print(f"has_watched_drift={'true' if has_watched_drift else 'false'}")
    print(f"has_digest_drift={'true' if has_digest_drift else 'false'}")
    print(
        f"has_any_drift={'true' if (has_watched_drift or has_digest_drift) else 'false'}"
    )


if __name__ == "__main__":
    main()
