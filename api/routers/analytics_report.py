"""
Analytics Report router - generate and manage AI-powered analytics reports.

Uses claude CLI subprocess (same pattern as session_title_generator.py) to
generate narrative reports from analytics data. Reports are stored as JSON
files in ~/.claude_karma/analytics-reports/.
"""

import json
import logging
import os
import re
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from config import settings

router = APIRouter()
logger = logging.getLogger(__name__)

MAX_REPORTS = 50

# ── Pydantic models ───────────────────────────────────────────────────────────


class StatsSnapshot(BaseModel):
    total_sessions: int = 0
    estimated_cost_usd: float = 0.0
    cache_hit_rate: float = 0.0
    total_tokens: int = 0


class ReportMeta(BaseModel):
    id: str
    created_at: str
    filter_label: str
    preview: str = Field("", description="First 150 chars of report text")
    stats_snapshot: StatsSnapshot


class ReportFull(ReportMeta):
    report: str


class GenerateReportRequest(BaseModel):
    filter_label: str
    analytics: dict = Field(..., description="Full analytics object from the frontend")


# ── Disk helpers ──────────────────────────────────────────────────────────────


def _reports_dir() -> Path:
    d = settings.karma_base / "analytics-reports"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _report_filename(created_at: str, report_id: str) -> str:
    return f"{created_at[:10]}-{report_id}.json"


def _save_report(
    report_id: str,
    created_at: str,
    filter_label: str,
    report_text: str,
    analytics: dict,
) -> None:
    payload = {
        "id": report_id,
        "created_at": created_at,
        "filter_label": filter_label,
        "report": report_text,
        "stats_snapshot": {
            "total_sessions": analytics.get("total_sessions", 0),
            "estimated_cost_usd": analytics.get("estimated_cost_usd", 0.0),
            "cache_hit_rate": analytics.get("cache_hit_rate", 0.0),
            "total_tokens": analytics.get("total_tokens", 0),
        },
    }
    path = _reports_dir() / _report_filename(created_at, report_id)
    path.write_text(json.dumps(payload, indent=2))


def _prune_old_reports() -> None:
    """Keep only the MAX_REPORTS most recent reports."""
    files = sorted(
        _reports_dir().glob("*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for old in files[MAX_REPORTS:]:
        try:
            old.unlink()
        except OSError:
            pass


def _parse_report_file(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _load_all_reports() -> list[ReportMeta]:
    files = sorted(
        _reports_dir().glob("*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    result = []
    for f in files[:MAX_REPORTS]:
        data = _parse_report_file(f)
        if not data:
            continue
        try:
            result.append(
                ReportMeta(
                    id=data["id"],
                    created_at=data["created_at"],
                    filter_label=data.get("filter_label", ""),
                    preview=data.get("report", "")[:150],
                    stats_snapshot=StatsSnapshot(**data.get("stats_snapshot", {})),
                )
            )
        except Exception as exc:
            logger.warning("Skipping malformed report file %s: %s", f, exc)
            continue
    return result


def _valid_report_id(report_id: str) -> bool:
    return bool(re.match(r"^[0-9a-f]{8}$", report_id))


def _find_report_file(report_id: str) -> Optional[Path]:
    matches = list(_reports_dir().glob(f"*-{report_id}.json"))
    return matches[0] if matches else None


# ── Prompt builder ────────────────────────────────────────────────────────────


def _build_prompt(analytics: dict, filter_label: str) -> str:
    td = analytics.get("time_distribution", {})
    models = analytics.get("models_categorized", {})
    tools = analytics.get("tools_used", {})
    top_tools = sorted(tools.items(), key=lambda x: x[1], reverse=True)[:5]
    peak_hours = analytics.get("peak_hours", [])
    peak_str = ", ".join(f"{h}:00" for h in peak_hours) if peak_hours else "unknown"
    models_str = (
        ", ".join(f"{m}: {c}" for m, c in sorted(models.items(), key=lambda x: x[1], reverse=True))
        or "none"
    )
    tools_str = ", ".join(f"{t}: {c}" for t, c in top_tools) or "none"

    return f"""You are analyzing Claude Code usage data for a software developer. \
Write a concise 3–4 paragraph analytical report in second person ("You've been..."). \
Use **bold** for key numbers. End with a "## Suggestions" section with 2–3 bullet points.

PERIOD: {filter_label}
Sessions: {analytics.get("total_sessions", 0)} | Cost: ${analytics.get("estimated_cost_usd", 0):.2f} | Cache hit: {analytics.get("cache_hit_rate", 0) * 100:.1f}%
Tokens: {analytics.get("total_tokens", 0):,} total (in: {analytics.get("total_input_tokens", 0):,} / out: {analytics.get("total_output_tokens", 0):,})
Duration: {analytics.get("total_duration_seconds", 0) / 3600:.1f}h | Active projects: {analytics.get("projects_active", 0)}
Peak hours: {peak_str} | Dominant period: {td.get("dominant_period", "Unknown")}
Time split: morning {td.get("morning_pct", 0):.0f}% / afternoon {td.get("afternoon_pct", 0):.0f}% / evening {td.get("evening_pct", 0):.0f}% / night {td.get("night_pct", 0):.0f}%
Models: {models_str}
Top tools: {tools_str}

Write the report now:"""


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("", response_model=ReportFull)
def generate_report(req: GenerateReportRequest) -> ReportFull:
    """
    Generate an AI analytics report via the claude CLI subprocess.
    Saves the result to ~/.claude_karma/analytics-reports/ and returns it.
    """
    if not req.analytics or req.analytics.get("total_sessions", 0) == 0:
        raise HTTPException(
            status_code=400,
            detail="no_data",
        )

    prompt = _build_prompt(req.analytics, req.filter_label)

    try:
        env = os.environ.copy()
        env.pop("CLAUDECODE", None)  # allow nested claude invocation

        result = subprocess.run(
            [
                "claude",
                "-p",
                prompt,
                "--model",
                "haiku",
                "--no-session-persistence",
                "--output-format",
                "text",
            ],
            capture_output=True,
            text=True,
            timeout=45,
            env=env,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail="claude_not_found") from e
    except subprocess.TimeoutExpired as e:
        raise HTTPException(status_code=504, detail="timeout") from e
    except OSError as e:
        logger.error("subprocess OSError: %s", e)
        raise HTTPException(status_code=503, detail="generation_failed") from e

    stderr_lower = (result.stderr or "").lower()

    if result.returncode != 0:
        if any(kw in stderr_lower for kw in ("rate limit", "quota", "usage limit", "too many")):
            raise HTTPException(status_code=429, detail="rate_limit")
        if any(kw in stderr_lower for kw in ("auth", "api key", "unauthorized", "credential")):
            raise HTTPException(status_code=503, detail="auth_error")
        logger.warning(
            "claude subprocess failed (rc=%d): %s", result.returncode, result.stderr[:200]
        )
        raise HTTPException(status_code=503, detail="generation_failed")

    report_text = result.stdout.strip()
    if not report_text:
        raise HTTPException(status_code=503, detail="generation_failed")

    report_id = uuid.uuid4().hex[:8]
    created_at = datetime.now(timezone.utc).isoformat()

    _save_report(report_id, created_at, req.filter_label, report_text, req.analytics)
    _prune_old_reports()

    return ReportFull(
        id=report_id,
        created_at=created_at,
        filter_label=req.filter_label,
        preview=report_text[:150],
        stats_snapshot=StatsSnapshot(
            total_sessions=req.analytics.get("total_sessions", 0),
            estimated_cost_usd=req.analytics.get("estimated_cost_usd", 0.0),
            cache_hit_rate=req.analytics.get("cache_hit_rate", 0.0),
            total_tokens=req.analytics.get("total_tokens", 0),
        ),
        report=report_text,
    )


@router.get("/{report_id}", response_model=ReportFull)
def get_report(report_id: str) -> ReportFull:
    """Get the full content of a saved analytics report."""
    if not _valid_report_id(report_id):
        raise HTTPException(status_code=400, detail="Invalid report ID")
    path = _find_report_file(report_id)
    if not path:
        raise HTTPException(status_code=404, detail="Report not found")
    data = _parse_report_file(path)
    if not data:
        raise HTTPException(status_code=500, detail="Failed to read report file")
    return ReportFull(
        id=data["id"],
        created_at=data["created_at"],
        filter_label=data.get("filter_label", ""),
        preview=data.get("report", "")[:150],
        stats_snapshot=StatsSnapshot(**data.get("stats_snapshot", {})),
        report=data.get("report", ""),
    )


@router.get("", response_model=list[ReportMeta])
def list_reports() -> list[ReportMeta]:
    """List saved analytics reports, most recent first (max 50)."""
    return _load_all_reports()


@router.delete("/{report_id}", status_code=204)
def delete_report(report_id: str) -> None:
    """Delete a saved analytics report by ID."""
    if not _valid_report_id(report_id):
        raise HTTPException(status_code=400, detail="Invalid report ID")
    path = _find_report_file(report_id)
    if not path:
        raise HTTPException(status_code=404, detail="Report not found")
    path.unlink(missing_ok=True)
