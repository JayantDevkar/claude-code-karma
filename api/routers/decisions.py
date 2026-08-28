"""
Decision ledger.

GET /projects/{encoded_name}/decisions — the curated decision ledger for a
project: the significant choices made across its sessions (human and AI),
each with intent, what was chosen, why, and links to evidence.

First-draft implementation: ledgers are hand-curated JSON files under
api/data/decision_ledgers/{encoded_name}.json. Automated extraction from
session JSONL is a later phase — the file format is the contract it will
have to produce.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(tags=["decisions"])

LEDGERS_DIR = Path(__file__).resolve().parent.parent / "data" / "decision_ledgers"


@router.get("/projects/{encoded_name}/decisions")
def project_decisions(encoded_name: str) -> dict:
    """
    Return the decision ledger for a project, newest decision first.
    404 when no ledger exists for the project (the frontend hides the tab's
    content behind an empty state in that case).
    """
    # encoded_name is used as a filename — reject anything path-like.
    if "/" in encoded_name or "\\" in encoded_name or ".." in encoded_name:
        raise HTTPException(status_code=400, detail="Invalid project name")

    ledger_path = LEDGERS_DIR / f"{encoded_name}.json"
    if not ledger_path.is_file():
        raise HTTPException(status_code=404, detail="No decision ledger for this project")

    try:
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.exception("Failed to read decision ledger %s", ledger_path)
        raise HTTPException(status_code=500, detail="Failed to read decision ledger") from None

    decisions = ledger.get("decisions", [])
    decisions.sort(key=lambda d: d.get("date", ""), reverse=True)

    # Index by id so the frontend can resolve supersedes-links to titles.
    by_id = {d["id"]: d for d in decisions if "id" in d}
    for d in decisions:
        target = d.get("supersedes")
        if target and target in by_id:
            d["supersedes_title"] = by_id[target].get("title")

    ledger["decisions"] = decisions
    return ledger
