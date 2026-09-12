"""
Project decision workflow.

GET /projects/{encoded_name}/workflow — the curated decision workflow for a
project, shaped as a set of threads. Each thread is exactly one topic: a
tier-1 root node (feature / milestone / scope / design) with a chronological
spine of tier-2 events (process / reversal / review). A tier-2 event may
carry tier-3 sub-nodes (waiver / correction).

First-draft implementation: workflows are hand-curated JSON files under
api/data/workflows/{encoded_name}.json. Node labels ("Review 3.1"), tiers and
supersedes titles are derived here so the curated file never has to keep them
in sync — the file is the contract an automated extractor will later produce.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(tags=["workflow"])

WORKFLOWS_DIR = Path(__file__).resolve().parent.parent / "data" / "workflows"

TIER1 = ("feature", "milestone", "scope", "design")
TIER2 = ("process", "reversal", "review")
TIER3 = ("waiver", "correction")

TIER_OF: dict[str, int] = (
    {k: 1 for k in TIER1} | {k: 2 for k in TIER2} | {k: 3 for k in TIER3}
)

KIND_WORD: dict[str, str] = {
    "feature": "Feature",
    "milestone": "Milestone",
    "scope": "Scope",
    "design": "Design",
    "process": "Process",
    "reversal": "Reversal",
    "review": "Review",
    "waiver": "Waiver",
    "correction": "Correction",
}


def _derive_thread(thread: dict, ordinal: int) -> dict:
    """
    Attach ``ordinal`` to the thread and ``tier`` + ``label`` to every node.

    Labelling convention (matches the curator's shorthand):
    - the major number is the thread ordinal
    - the first node of a given kind in a thread is ``"<Kind> <ordinal>"``
    - each repeat gets a minor suffix: ``"Review 3"`` → ``"Review 3.1"`` → …
    """
    root = thread["root"]
    root["tier"] = 1
    root["label"] = f"{KIND_WORD.get(root['kind'], 'Topic')} {ordinal}"

    nodes = sorted(thread.get("nodes", []), key=lambda n: n.get("date", ""))
    seen_by_kind: dict[str, int] = {}
    for node in nodes:
        kind = node["kind"]
        node["tier"] = TIER_OF.get(kind, 2)
        seen_by_kind[kind] = seen_by_kind.get(kind, 0) + 1
        count = seen_by_kind[kind]
        suffix = "" if count == 1 else f".{count - 1}"
        node["label"] = f"{KIND_WORD.get(kind, kind.title())} {ordinal}{suffix}"

    thread["ordinal"] = ordinal
    thread["nodes"] = nodes
    return thread


@router.get("/projects/{encoded_name}/workflow")
def project_workflow(encoded_name: str) -> dict:
    """
    Return the decision workflow for a project, threads ordered oldest-first.

    404 when no workflow exists for the project (the page shows an empty state
    in that case).
    """
    # encoded_name is used as a filename — reject anything path-like.
    if "/" in encoded_name or "\\" in encoded_name or ".." in encoded_name:
        raise HTTPException(status_code=400, detail="Invalid project name")

    path = WORKFLOWS_DIR / f"{encoded_name}.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="No workflow for this project")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.exception("Failed to read workflow %s", path)
        raise HTTPException(
            status_code=500, detail="Failed to read workflow"
        ) from None

    threads = sorted(
        data.get("threads", []), key=lambda t: t["root"].get("date", "")
    )
    data["threads"] = [_derive_thread(t, i + 1) for i, t in enumerate(threads)]

    # Resolve supersedes-links to the target's derived label + title so the
    # drawer can render a readable back-reference.
    by_id: dict[str, dict] = {}
    for thread in data["threads"]:
        by_id[thread["root"]["id"]] = thread["root"]
        for node in thread["nodes"]:
            by_id[node["id"]] = node
    for node in by_id.values():
        target = node.get("supersedes")
        if target and target in by_id:
            node["supersedes_title"] = by_id[target].get("title")
            node["supersedes_label"] = by_id[target].get("label")

    return data
