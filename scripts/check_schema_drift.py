#!/usr/bin/env python3
"""
Detects drift between karma's vendored Claude Code settings snapshots and the
live upstream sources. Used by .github/workflows/schema-drift.yml — not meant
to be run standalone against real files outside that workflow's temp dir, but
safe to run locally against any pair of schema/reference files for testing.

The vendored snapshots (schema/claude-code-settings.schema.json,
schema/settings-reference.md) are deliberately trimmed to only the ~12 keys
in schema/watched-keys.json — the settings karma's Settings page actually
reads or writes — not the full ~150-property upstream schema. The live
sources fetched by the workflow are the full thing; this script trims them
down to the same watched-key scope (filter_schema_to_watched_keys,
filter_reference_to_watched_keys) before comparing, so the diff is always
apples-to-apples and the snapshot-refresh step never re-inflates the vendored
files back to full size.

Two kinds of drift get different treatment, both scoped to the watched keys:

  - "watched" drift: a watched key's JSON schema definition changed shape,
    enum, or default, or disappeared from the schema entirely. High
    priority: it can mean karma's UI shows a stale default, offers a value
    Claude Code no longer accepts, or silently no-ops -- the exact
    "spellcheck was on but did nothing" failure that motivated this
    feature. -> a `schema-drift` issue.

  - everything else that changed within the watched keys' own schema/doc
    content but that the per-key structural comparison above wouldn't catch
    (e.g. a $defs subschema a watched key references, like `permissionRule`,
    or reference-doc wording changing without a schema shape change) -> a
    low-priority `schema-drift-digest` issue.

Prints `key=value` GitHub Actions output lines to stdout; the workflow
redirects them into $GITHUB_OUTPUT. Writes issue body markdown files, plus
the trimmed live schema/reference for the snapshot-refresh step to use, into
the given output directory when there's something to report.
"""

import argparse
import difflib
import json
import re
from pathlib import Path

# The live upstream schema has 150+ top-level properties. Anything drastically
# smaller is a sign of a bad fetch (a WAF interstitial that happens to be
# valid JSON, a truncated response, an API error body) rather than a real
# schema -- and per-key drift comparison can't tell the difference, since
# from its point of view every watched key just looks "removed". Without this
# check, a bad fetch would both fire a false schema-drift issue for every
# watched key AND open a PR proposing the garbage as the new vendored
# baseline, silently degrading api/routers/settings.py's live validator if
# that PR is merged without close scrutiny.
#
# Only ever applied to the *raw, freshly-fetched* live schema, before it gets
# trimmed down to the watched-key subset below -- the vendored schema on disk
# is deliberately tiny now (only the watched keys), so this threshold would
# never make sense applied to it.
MIN_EXPECTED_SCHEMA_PROPERTIES = 50


def sanity_check_schema(schema: dict, source: str) -> None:
    """Raise if `schema` doesn't look like a real, complete Claude Code settings schema."""
    properties = schema.get("properties")
    count = len(properties) if isinstance(properties, dict) else 0
    if count < MIN_EXPECTED_SCHEMA_PROPERTIES:
        raise ValueError(
            f"{source} schema has only {count} top-level properties (expected at "
            f"least {MIN_EXPECTED_SCHEMA_PROPERTIES}). This looks like a bad fetch, "
            "not a real settings schema -- refusing to treat it as ground truth."
        )


def filter_schema_to_watched_keys(schema: dict, watched_keys: list) -> dict:
    """Trim a full settings schema down to only the properties karma actually
    reads or writes, plus whatever `$defs` those properties transitively
    `$ref` (so nested strict subschemas like `permissionRule` stay intact).

    Keeps everything else about the schema (title, description,
    additionalProperties, etc.) untouched -- only `properties` and `$defs`
    shrink. Silently drops any watched key the schema doesn't define (e.g.
    `spellcheck`, which the community JSON schema doesn't model even though
    it's a real, documented setting) rather than erroring, matching how
    `diff_watched_keys` already treats a missing key as legitimate drift to
    report, not a bug in this function.
    """
    all_props = schema.get("properties", {})
    all_defs = schema.get("$defs", {})

    kept_props = {k: all_props[k] for k in watched_keys if k in all_props}

    # Walk $refs reachable from the kept properties (one level of $defs is
    # enough for this schema -- $defs don't currently reference each other).
    referenced_defs = set()
    for prop_schema in kept_props.values():
        referenced_defs.update(re.findall(r"#/\$defs/(\w+)", json.dumps(prop_schema)))
    kept_defs = {k: all_defs[k] for k in referenced_defs if k in all_defs}

    trimmed = dict(schema)
    trimmed["properties"] = kept_props
    if kept_defs:
        trimmed["$defs"] = kept_defs
    elif "$defs" in trimmed:
        del trimmed["$defs"]
    return trimmed


def filter_reference_to_watched_keys(text: str, watched_keys: list) -> str:
    """Trim the settings-reference markdown down to the overview-table rows
    and `### `key`` detail sections for only the watched keys, in the same
    format `schema/settings-reference.md` is vendored in. Mirrors the
    hand-built trim that produced that file, so the live doc gets reduced to
    an apples-to-apples shape before diffing against it.
    """
    lines = text.splitlines(keepends=True)
    heading_idx = [i for i, l in enumerate(lines) if l.startswith("## ") or l.startswith("### ")]

    table_rows = {}
    for line in lines:
        m = re.match(r"^\|\s*\[`([a-zA-Z0-9_]+)`\]", line)
        if m and m.group(1) in watched_keys:
            table_rows[m.group(1)] = line.rstrip("\n")

    table_header_lines = []
    for i, line in enumerate(lines):
        if line.startswith("|") and set(line.strip()) <= set("|-: "):
            table_header_lines = [lines[i - 1].rstrip("\n"), line.rstrip("\n")]
            break

    key_to_line = {}
    for i in heading_idx:
        m = re.match(r"^### `([a-zA-Z0-9_]+)`", lines[i])
        if m and m.group(1) in watched_keys:
            key_to_line[m.group(1)] = i

    sections = {}
    for key, start in key_to_line.items():
        end = next((h for h in heading_idx if h > start), len(lines))
        sections[key] = "".join(lines[start:end]).rstrip("\n")

    out = [
        # Deliberately `## ` (not `# `): the workflow's JSX-preamble-stripping
        # normalization (`awk '/^## /{f=1} f'`) runs over this file too, and
        # would silently zero it out if it started with a level-1 heading.
        "## Claude Code settings reference (trimmed)\n",
        "\n",
        "Curated subset of the live settings reference, trimmed to only the keys in "
        "`schema/watched-keys.json` -- the settings karma's Settings page actually reads "
        "or writes. Kept in sync by `.github/workflows/schema-drift.yml`.\n",
        "\n",
    ]
    if table_header_lines:
        out += [table_header_lines[0] + "\n", table_header_lines[1] + "\n"]
    for key in watched_keys:
        if key in table_rows:
            out.append(table_rows[key] + "\n")
    out.append("\n")
    for key in watched_keys:
        if key in sections:
            out.append(sections[key] + "\n\n")

    return "".join(out)


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

    # `old_schema`/`old_reference` are the vendored files on disk -- already
    # trimmed to the watched-key subset (see filter_schema_to_watched_keys /
    # filter_reference_to_watched_keys), so no size sanity check applies to
    # them the way it does to a network fetch.
    old_schema = load_json(args.old_schema)
    old_reference_text = args.old_reference.read_text(encoding="utf-8")
    watched_keys = load_json(args.watched_keys)["keys"]

    # `new_schema`/`new_reference` are the raw, freshly-fetched live sources
    # -- the full ~150-property upstream schema and full reference doc, not
    # yet trimmed. Sanity-check the raw fetch before trusting it for
    # anything: a bad fetch (WAF page, truncated response) that happened to
    # be valid JSON would otherwise both fire a false schema-drift issue for
    # every watched key AND get proposed as the new vendored baseline.
    new_schema_raw = load_json(args.new_schema)
    sanity_check_schema(new_schema_raw, "live")
    new_reference_text_raw = args.new_reference.read_text(encoding="utf-8")

    # Trim the live fetch down to the same watched-key scope as the vendored
    # files before comparing -- otherwise every run would show "everything
    # outside our 12 keys just vanished" as spurious drift, and the
    # snapshot-update step below would re-inflate the vendored files back to
    # the full ~150-property schema the moment any real drift fires.
    new_schema = filter_schema_to_watched_keys(new_schema_raw, watched_keys)
    new_reference_text = filter_reference_to_watched_keys(new_reference_text_raw, watched_keys)
    # Serialize once and reuse for both the diff and the snapshot-update
    # output below -- computing this separately in two places previously
    # left the diffed text missing the trailing newline the vendored file
    # (and the written-out snapshot) always has, which showed up as a
    # spurious "no newline at end of file"-style line in every digest.
    new_schema_text = json.dumps(new_schema, indent=2, sort_keys=True) + "\n"

    watched_drift = diff_watched_keys(old_schema, new_schema, watched_keys)

    schema_diff = "".join(
        difflib.unified_diff(
            load_lines(args.old_schema),
            new_schema_text.splitlines(keepends=True),
            fromfile="vendored schema",
            tofile="live schema (trimmed to watched keys)",
        )
    )
    reference_diff = "".join(
        difflib.unified_diff(
            old_reference_text.splitlines(keepends=True),
            new_reference_text.splitlines(keepends=True),
            fromfile="vendored reference",
            tofile="live reference (trimmed to watched keys)",
        )
    )

    has_watched_drift = bool(watched_drift)
    has_digest_drift = bool(schema_diff.strip() or reference_diff.strip())

    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Trimmed live content, for the workflow's "update vendored snapshots"
    # step to copy from -- never the raw fetch, which would defeat the whole
    # point of trimming by re-growing the vendored files on the next drift.
    (args.output_dir / "trimmed-live-schema.json").write_text(new_schema_text, encoding="utf-8")
    (args.output_dir / "trimmed-live-reference.md").write_text(
        new_reference_text, encoding="utf-8"
    )

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
