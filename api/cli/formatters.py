"""Output formatters for karma CLI."""
from tabulate import tabulate


def _truncate(text: str, max_len: int = 50) -> str:
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _format_duration(seconds: float | None) -> str:
    if not seconds:
        return "-"
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"{minutes}min"
    hours = minutes // 60
    remaining = minutes % 60
    return f"{hours}h{remaining:02d}m"


def format_table(sessions: list[dict]) -> str:
    """Format sessions as a human-readable table."""
    if not sessions:
        return "No sessions found."

    rows = []
    for s in sessions:
        rows.append([
            s["uuid"][:8],
            s.get("git_branch") or "-",
            (s.get("start_time") or "")[:10],
            _format_duration(s.get("duration_seconds")),
            s.get("message_count") or 0,
            f"${s.get('total_cost', 0):.2f}",
            _truncate(s.get("session_titles") or s.get("initial_prompt") or "", 40),
        ])

    headers = ["UUID", "BRANCH", "DATE", "DURATION", "MSGS", "COST", "TITLE/PROMPT"]
    return tabulate(rows, headers=headers, tablefmt="plain")


def format_for_claude(sessions: list[dict]) -> str:
    """Format sessions as structured markdown for Claude Code consumption."""
    if not sessions:
        return "No sessions found."

    parts = []
    for s in sessions:
        uuid = s["uuid"]
        branch = s.get("git_branch") or "unknown"
        date = (s.get("start_time") or "")[:10]
        title = s.get("session_titles") or ""
        prompt = s.get("initial_prompt") or ""
        duration = _format_duration(s.get("duration_seconds"))
        msgs = s.get("message_count", 0)
        cost = s.get("total_cost", 0)
        skills = s.get("skills") or ""
        tools = s.get("tools") or ""
        project = s.get("project_path") or ""

        section = f"## Session {uuid[:12]} — {branch} — {date}\n"
        if title:
            section += f"**Title:** {title}\n"
        if prompt:
            section += f"**Initial prompt:** {_truncate(prompt, 200)}\n"
        section += f"**Duration:** {duration} | **Messages:** {msgs} | **Cost:** ${cost:.2f}\n"
        if skills:
            section += f"**Skills used:** {skills}\n"
        if tools:
            section += f"**Tools used:** {tools}\n"
        if project:
            section += f"**Project:** {project}\n"
        section += f"**Full UUID:** {uuid}\n"

        parts.append(section)

    return "\n---\n\n".join(parts)
