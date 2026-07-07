"""
Cron job + fire + state-snapshot models.

Cron in Claude Code is session-scoped and in-memory: CronCreate / CronList /
CronDelete operate on a per-session table that lives only in the running CLI
process, with a 7-day TTL via `claude --resume`. There is no on-disk file
written by Claude itself.

Karma reconstructs cron history from JSONL tool calls. For ground-truth
live state, the optional `cron_state_capture.py` PostToolUse hook writes
snapshots of CronList responses; those land in `cron_state_snapshots`.

Cron fires are NOT persisted. They are derived on read by joining cron_jobs
to message_uuids and matching scheduled times against assistant turn
timestamps. This keeps the schema decoupled from the matching window.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class CronDeletionReason(str, Enum):
    """Why a cron job is no longer active."""

    CRON_DELETE = "CronDelete"  # Explicit CronDelete tool call
    SESSION_END = "session_end"  # Session ended; cron is in-memory, so it died with it
    EXPIRY = "expiry"  # 7-day TTL passed without a resume
    UNKNOWN = "unknown"  # Live-state hook said it's gone, source uncertain


class CronStateTriggerEvent(str, Enum):
    """Which event caused a cron-state snapshot to be captured."""

    CRON_CREATE = "CronCreate"
    CRON_DELETE = "CronDelete"
    CRON_LIST = "CronList"
    SESSION_START = "session_start"


class CronFireInferenceSource(str, Enum):
    """Where a fire record came from. Hook == ground truth; jsonl == inferred."""

    JSONL = "jsonl"
    HOOK = "hook"


class CronJob(BaseModel):
    """
    A scheduled job created via CronCreate. Reconstructed from JSONL.

    deleted_at + deleted_via are populated together (DB coherence CHECK). A
    None pair means the job appeared active at the end of the JSONL — but
    because cron is in-memory only, it may have died with the session. The
    `ttl_expires_at` field (created_at + 7d) tells the UI when even
    `--resume` can no longer revive it.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    id: int = Field(..., description="DB primary key")
    session_uuid: str = Field(..., description="Session that created the job")
    tool_use_id: str = Field(
        ..., description="toolu_... ID of the CronCreate call (globally unique)"
    )
    cron_id: Optional[str] = Field(
        None,
        description=(
            "8-character cron job ID returned in the CronCreate tool_result. None "
            "when the result has not yet been parsed."
        ),
    )
    cron_expression: str = Field(..., description="5-field cron expression, e.g. '*/5 * * * *'")
    prompt: str = Field(..., description="Prompt the cron job will run when it fires")
    recurring: bool = Field(False, description="True for recurring jobs; False for one-shots")
    created_at: datetime = Field(..., description="Timestamp of the CronCreate tool_use")
    deleted_at: Optional[datetime] = Field(
        None, description="None when still active; set together with deleted_via"
    )
    deleted_via: Optional[CronDeletionReason] = Field(
        None, description="Why the job is no longer active; None when still active"
    )
    ttl_expires_at: datetime = Field(
        ...,
        description="created_at + 7 days. After this point even --resume cannot revive the job.",
    )
    create_message_uuid: Optional[str] = Field(
        None, description="UUID of the assistant message that contained the CronCreate"
    )

    @property
    def is_active_in_history(self) -> bool:
        """True when this job has not been explicitly deleted in JSONL."""
        return self.deleted_at is None

    @property
    def seconds_to_ttl_expiry(self) -> float:
        """Seconds until the 7-day TTL expires. Negative if already expired."""
        return (self.ttl_expires_at - datetime.now(self.ttl_expires_at.tzinfo)).total_seconds()


class CronFire(BaseModel):
    """
    A single inferred (or hook-recorded) fire of a cron job.

    Derived on read by the query helpers — NOT stored in the DB. The
    `inference_confidence` field is 1.0 when the fire came from the live
    hook, and <1.0 when inferred from JSONL by matching assistant turn
    timestamps against the cron expression's scheduled times.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    cron_job_id: int = Field(..., description="DB id of the parent cron_jobs row")
    fired_at: datetime = Field(..., description="When the fire is believed to have occurred")
    triggering_message_uuid: Optional[str] = Field(
        None, description="UUID of the assistant message that was matched as the fire"
    )
    inference_confidence: float = Field(
        ..., description="1.0 = ground truth from hook; <1.0 = inferred from JSONL"
    )
    inference_source: CronFireInferenceSource = Field(
        ..., description="Where this fire came from: 'jsonl' or 'hook'"
    )
    outcome_excerpt: Optional[str] = Field(
        None, description="First ~500 chars of the assistant response, when available"
    )


class CronStateSnapshot(BaseModel):
    """
    A snapshot of Claude's in-memory cron table at a point in time.

    Written by the optional cron_state_capture.py PostToolUse hook on every
    CronCreate / CronDelete / CronList tool call. payload_json is the raw
    CronList result; karma does not parse its internal structure so future
    Claude Code schema changes do not require a migration here.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    id: int = Field(..., description="DB primary key")
    session_uuid: str = Field(..., description="Session the snapshot belongs to")
    captured_at: datetime = Field(..., description="When the hook fired")
    trigger_event: CronStateTriggerEvent = Field(
        ..., description="Which tool call caused the snapshot to be taken"
    )
    payload_json: str = Field(..., description="Raw CronList tool_response as JSON text")
