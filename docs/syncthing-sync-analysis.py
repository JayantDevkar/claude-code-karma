"""Generate PDF: Syncthing Sync Analysis for Claude Karma."""

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, KeepTogether,
)

# ── Colors ─────────────────────────────────────────────────────────────
DARK = colors.Color(0.15, 0.15, 0.15)
MID = colors.Color(0.4, 0.4, 0.4)
LIGHT = colors.Color(0.88, 0.88, 0.88)
ACCENT = colors.Color(0.27, 0.27, 0.55)  # muted indigo
WHITE = colors.white

# ── Styles ─────────────────────────────────────────────────────────────
styles = getSampleStyleSheet()

title_style = ParagraphStyle(
    "DocTitle", parent=styles["Title"],
    fontSize=22, leading=26, textColor=DARK, spaceAfter=4,
)
subtitle_style = ParagraphStyle(
    "DocSubtitle", parent=styles["Normal"],
    fontSize=11, leading=14, textColor=MID, spaceAfter=18, alignment=1,
)
h1 = ParagraphStyle(
    "H1", parent=styles["Heading1"],
    fontSize=15, leading=18, textColor=ACCENT, spaceBefore=16, spaceAfter=6,
)
h2 = ParagraphStyle(
    "H2", parent=styles["Heading2"],
    fontSize=12, leading=15, textColor=DARK, spaceBefore=12, spaceAfter=4,
)
h3 = ParagraphStyle(
    "H3", parent=styles["Heading3"],
    fontSize=10, leading=13, textColor=MID, spaceBefore=8, spaceAfter=3,
)
body = ParagraphStyle(
    "Body", parent=styles["Normal"],
    fontSize=9, leading=13, textColor=DARK, spaceAfter=6,
)
code_style = ParagraphStyle(
    "Code", parent=styles["Normal"],
    fontName="Courier", fontSize=7.5, leading=10,
    textColor=DARK, spaceAfter=6, leftIndent=12,
)
bullet_style = ParagraphStyle(
    "Bullet", parent=body,
    leftIndent=18, bulletIndent=6, spaceAfter=3,
)

# ── Table helper ───────────────────────────────────────────────────────
def make_table(headers, rows, col_widths=None):
    data = [headers] + rows
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("FONTSIZE", (0, 1), (-1, -1), 7.5),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("BACKGROUND", (0, 0), (-1, 0), LIGHT),
        ("TEXTCOLOR", (0, 0), (-1, -1), DARK),
        ("GRID", (0, 0), (-1, -1), 0.4, LIGHT),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, colors.Color(0.96, 0.96, 0.96)]),
    ]))
    return t

def hr():
    return HRFlowable(width="100%", thickness=1, color=LIGHT, spaceBefore=6, spaceAfter=6)

# ── Build document ─────────────────────────────────────────────────────
OUTPUT = "syncthing-sync-analysis.pdf"
doc = SimpleDocTemplate(
    OUTPUT, pagesize=letter,
    leftMargin=0.7*inch, rightMargin=0.7*inch,
    topMargin=0.6*inch, bottomMargin=0.6*inch,
)
story = []

# ── Title page ─────────────────────────────────────────────────────────
story.append(Spacer(1, 40))
story.append(Paragraph("Syncthing Sync Analysis", title_style))
story.append(Paragraph("Claude Code Karma — Files Synced & Dashboard Features Enabled", subtitle_style))
story.append(hr())
story.append(Spacer(1, 8))
story.append(Paragraph(
    "This document describes what files are synced across machines using Syncthing, "
    "how the sync pipeline works, and what features/pages it enables in the Claude Karma dashboard.",
    body,
))

# ══════════════════════════════════════════════════════════════════════
# SECTION 1: Files Synced
# ══════════════════════════════════════════════════════════════════════
story.append(Paragraph("1. Files Synced Across Machines", h1))

story.append(Paragraph(
    "Syncthing syncs <b>Claude Code session data</b> between machines via shared folders "
    "under <font face='Courier' size='8'>~/.claude_karma/remote-sessions/</font>. "
    "The <font face='Courier' size='8'>SessionPackager</font> (cli/karma/packager.py) "
    "discovers and stages files from Claude Code's local storage.",
    body,
))

story.append(Paragraph("1.1 Per-Project Session Package", h2))

story.append(make_table(
    ["File / Directory", "Source Location", "Synced Path"],
    [
        ["Session JSONL", "~/.claude/projects/{encoded}/*.jsonl", "remote-sessions/{user}/{encoded}/sessions/{uuid}.jsonl"],
        ["Subagent conversations", "{encoded}/{uuid}/subagents/agent-*.jsonl", "...sessions/{uuid}/subagents/"],
        ["Tool results", "{encoded}/{uuid}/tool-results/toolu_*.txt", "...sessions/{uuid}/tool-results/"],
        ["Todo items", "~/.claude/todos/{uuid}-*.json", "...{encoded}/todos/"],
        ["Worktree sessions", "~/.claude/projects/{worktree-encoded}/*.jsonl", "Packaged into the same outbox"],
        ["Manifest", "Generated at package time", "remote-sessions/{user}/{encoded}/manifest.json"],
    ],
    col_widths=[1.4*inch, 2.4*inch, 3.0*inch],
))

story.append(Spacer(1, 8))
story.append(Paragraph("1.2 Syncthing Folder Configuration", h2))

story.append(Paragraph(
    "Each user/project pair creates <b>two Syncthing shared folders</b> "
    "(configured in cli/karma/main.py):",
    body,
))

story.append(make_table(
    ["Folder ID Pattern", "Path", "Type", "Purpose"],
    [
        ["karma-out-{my_user}-{project}", "~/.claude_karma/remote-sessions/{my_user}/{encoded}/", "sendonly", "My sessions --> teammates"],
        ["karma-out-{their_user}-{project}", "~/.claude_karma/remote-sessions/{their_user}/{encoded}/", "receiveonly", "Their sessions --> my machine"],
    ],
    col_widths=[1.8*inch, 2.2*inch, 0.8*inch, 2.0*inch],
))

story.append(Spacer(1, 8))
story.append(Paragraph("1.3 What is NOT Synced", h2))

not_synced = [
    "Global ~/.claude/ config",
    "Credentials / API keys",
    "Unregistered projects (only explicitly added projects sync)",
    "sync-config.json (local identity file, 0600 permissions)",
    "SQLite metadata DB (~/.claude_karma/metadata.db)",
]
for item in not_synced:
    story.append(Paragraph(f"&bull; {item}", bullet_style))

# ══════════════════════════════════════════════════════════════════════
# SECTION 2: Manifest Format
# ══════════════════════════════════════════════════════════════════════
story.append(Paragraph("1.4 Manifest Format", h2))

story.append(Paragraph(
    "Each sync produces a <font face='Courier' size='8'>manifest.json</font> "
    "describing the snapshot (cli/karma/manifest.py):",
    body,
))

story.append(make_table(
    ["Field", "Description"],
    [
        ["version", "Schema version (currently 1)"],
        ["user_id", "Syncing user's identity (set during init)"],
        ["machine_id", "Auto-generated from hostname"],
        ["project_path", "Original project path on source machine"],
        ["project_encoded", "Claude-encoded project directory name"],
        ["synced_at", "ISO timestamp of sync"],
        ["session_count", "Number of sessions in this snapshot"],
        ["sessions[]", "List of {uuid, mtime, size_bytes, worktree_name, git_branch}"],
        ["sync_backend", "'ipfs', 'syncthing', or null"],
        ["previous_cid", "IPFS only: links to previous sync snapshot"],
    ],
    col_widths=[1.5*inch, 5.3*inch],
))

# ══════════════════════════════════════════════════════════════════════
# SECTION 3: Configuration & Identity
# ══════════════════════════════════════════════════════════════════════
story.append(Paragraph("1.5 Configuration & Identity (Local Only)", h2))

story.append(make_table(
    ["File", "Location", "Purpose"],
    [
        ["sync-config.json", "~/.claude_karma/sync-config.json", "User identity, Syncthing API key & device ID"],
        ["SQLite sync tables", "~/.claude_karma/metadata.db", "Teams, members, projects, events (4 tables)"],
    ],
    col_widths=[1.4*inch, 2.6*inch, 2.8*inch],
))

story.append(Paragraph(
    "SQLite tables: <font face='Courier' size='8'>sync_teams</font>, "
    "<font face='Courier' size='8'>sync_members</font>, "
    "<font face='Courier' size='8'>sync_team_projects</font>, "
    "<font face='Courier' size='8'>sync_events</font>",
    body,
))

story.append(PageBreak())

# ══════════════════════════════════════════════════════════════════════
# SECTION 4: Dashboard Features
# ══════════════════════════════════════════════════════════════════════
story.append(Paragraph("2. Dashboard Features Enabled by Sync", h1))

# ── /sync page ─────────────────────────────────────────────────────
story.append(Paragraph("2.1  /sync — Sync Setup & Overview", h2))

story.append(Paragraph(
    "Components: <font face='Courier' size='8'>SetupWizard.svelte</font>, "
    "<font face='Courier' size='8'>OverviewTab.svelte</font>, "
    "<font face='Courier' size='8'>ProjectTeamTab.svelte</font>",
    body,
))

story.append(make_table(
    ["Feature", "Description"],
    [
        ["Setup Wizard (3 steps)", "How It Works --> Install Syncthing --> Name Machine. Auto-detects Syncthing, OS-specific install commands, copies device ID"],
        ["Session Watcher Banner", "Start/stop filesystem watcher that auto-packages sessions. Shows running state, team name, uptime"],
        ["Stats Dashboard", "4 cards: Members Online (connected/total), Projects count, Sessions Shared, Sessions Received"],
        ["Pending Actions", "Lists pending folder offers from known team members with Accept All button"],
        ["Machine Details Card", "Shows user name, machine hostname, Syncthing version"],
        ["Reset Sync", "Tears down all sync config and returns to setup wizard"],
    ],
    col_widths=[1.6*inch, 5.2*inch],
))

# ── /team page ─────────────────────────────────────────────────────
story.append(Spacer(1, 6))
story.append(Paragraph("2.2  /team — Team Management", h2))

story.append(Paragraph(
    "Components: <font face='Courier' size='8'>TeamCard.svelte</font>, "
    "<font face='Courier' size='8'>CreateTeamDialog.svelte</font>, "
    "<font face='Courier' size='8'>JoinTeamDialog.svelte</font>",
    body,
))

story.append(make_table(
    ["Feature", "Description"],
    [
        ["Team Listing", "Grid of team cards showing name, backend, member/project counts"],
        ["Create Team", "Dialog to create a new team with syncthing backend"],
        ["Join Team", "Paste join code (team:user:device_id), auto-pairs Syncthing device, auto-accepts pending folders"],
    ],
    col_widths=[1.6*inch, 5.2*inch],
))

# ── /team/[name] page ──────────────────────────────────────────────
story.append(Spacer(1, 6))
story.append(Paragraph("2.3  /team/[name] — Team Detail", h2))

story.append(Paragraph(
    "Components: <font face='Courier' size='8'>TeamMemberCard</font>, "
    "<font face='Courier' size='8'>AddMemberDialog</font>, "
    "<font face='Courier' size='8'>JoinCodeCard</font>, "
    "<font face='Courier' size='8'>PendingDeviceCard</font>, "
    "<font face='Courier' size='8'>AddProjectDialog</font>",
    body,
))

story.append(make_table(
    ["Feature", "Description"],
    [
        ["Join Code", "Copyable code for teammates to join (team:user:device_id)"],
        ["Member Management", "Add/remove members by Syncthing device ID, shows connection status"],
        ["Pending Devices", "Unknown Syncthing devices trying to connect"],
        ["Project Management", "Add/remove projects to sync, shows per-project sync status"],
        ["Per-Project Status", "Local session count, packaged count, received counts per member, sync gap"],
    ],
    col_widths=[1.6*inch, 5.2*inch],
))

# ── Existing pages enhanced ────────────────────────────────────────
story.append(Spacer(1, 6))
story.append(Paragraph("2.4  Existing Pages Enhanced by Remote Sessions", h2))

story.append(Paragraph(
    "The <font face='Courier' size='8'>remote_sessions.py</font> service "
    "integrates synced data into existing views:",
    body,
))

story.append(make_table(
    ["Page", "Enhancement"],
    [
        ["/projects/[name]", "Session lists include source='remote' sessions from teammates alongside local ones"],
        ["/sessions (global)", "iter_all_remote_session_metadata() adds all remote sessions to the global browser"],
        ["/sessions/[uuid]", "find_remote_session() can load a remote session by UUID (full conversation, tools, subagents)"],
    ],
    col_widths=[1.6*inch, 5.2*inch],
))

# ══════════════════════════════════════════════════════════════════════
# SECTION 5: API Endpoints
# ══════════════════════════════════════════════════════════════════════
story.append(Spacer(1, 6))
story.append(Paragraph("3. API Endpoints Powering the Sync UI", h1))

story.append(Paragraph("3.1  Sync Status & Config  (/sync/*)", h2))

story.append(make_table(
    ["Method", "Endpoint", "Description"],
    [
        ["POST", "/sync/init", "Initialize sync identity"],
        ["GET", "/sync/status", "Config summary (user, teams, device)"],
        ["GET", "/sync/detect", "Syncthing installed / running / version"],
        ["POST", "/sync/reset", "Tear down all config"],
        ["GET", "/sync/devices", "List Syncthing devices + connection status"],
        ["GET", "/sync/projects", "Syncthing folder sync status (files, bytes, state)"],
        ["POST", "/sync/rescan", "Force rescan all folders"],
    ],
    col_widths=[0.6*inch, 2.2*inch, 4.0*inch],
))

story.append(Spacer(1, 6))
story.append(Paragraph("3.2  Team CRUD  (/sync/teams/*)", h2))

story.append(make_table(
    ["Method", "Endpoint", "Description"],
    [
        ["POST", "/sync/teams", "Create team"],
        ["DELETE", "/sync/teams/{name}", "Delete team"],
        ["GET", "/sync/teams", "List all teams with members/projects"],
        ["POST", "/sync/teams/join", "Join via code"],
        ["GET", "/sync/teams/{name}/join-code", "Get join code"],
        ["POST", "/sync/teams/{name}/members", "Add member"],
        ["DELETE", "/sync/teams/{name}/members/{name}", "Remove member"],
        ["POST", "/sync/teams/{name}/projects", "Add project"],
        ["DELETE", "/sync/teams/{name}/projects/{name}", "Remove project"],
        ["GET", "/sync/teams/{name}/project-status", "Per-project sync counts"],
    ],
    col_widths=[0.6*inch, 2.8*inch, 3.4*inch],
))

story.append(Spacer(1, 6))
story.append(Paragraph("3.3  Watcher & Pending", h2))

story.append(make_table(
    ["Method", "Endpoint", "Description"],
    [
        ["GET", "/sync/watch/status", "Watcher daemon status"],
        ["POST", "/sync/watch/start", "Start session watcher"],
        ["POST", "/sync/watch/stop", "Stop session watcher"],
        ["GET", "/sync/pending", "List pending folder offers"],
        ["POST", "/sync/pending/accept", "Accept all pending offers"],
        ["GET", "/sync/pending-devices", "Unknown devices trying to connect"],
        ["GET", "/sync/activity", "Sync events + bandwidth stats"],
    ],
    col_widths=[0.6*inch, 2.2*inch, 4.0*inch],
))

story.append(PageBreak())

# ══════════════════════════════════════════════════════════════════════
# SECTION 6: Data Flow
# ══════════════════════════════════════════════════════════════════════
story.append(Paragraph("4. Data Flow Summary", h1))

story.append(Paragraph(
    "The complete sync pipeline from session creation to dashboard display:",
    body,
))

flow_steps = [
    ("1. Session Creation", "Claude Code writes JSONL session files to ~/.claude/projects/{encoded}/{uuid}.jsonl"),
    ("2. File Watching", "SessionWatcher (watchdog library) detects .jsonl changes, debounces for 5 seconds"),
    ("3. Packaging", "SessionPackager copies JSONL + subagents + tool-results + todos into outbox at ~/.claude_karma/remote-sessions/{user_id}/{encoded}/"),
    ("4. Syncthing Transport", "Syncthing auto-detects change in sendonly folder, replicates via TLS 1.3 to paired devices"),
    ("5. Receiving", "Data arrives in receiveonly folder at ~/.claude_karma/remote-sessions/{remote_user}/{encoded}/ on the receiving machine"),
    ("6. API Layer", "remote_sessions.py reads the remote-sessions/ directory, builds SessionMetadata with source='remote'"),
    ("7. Dashboard", "Frontend displays remote sessions alongside local ones in project views, global sessions browser, and session detail pages"),
]

for step_title, step_desc in flow_steps:
    story.append(KeepTogether([
        Paragraph(f"<b>{step_title}</b>", body),
        Paragraph(step_desc, bullet_style),
    ]))

story.append(Spacer(1, 12))

# ── Key source files ───────────────────────────────────────────────
story.append(Paragraph("5. Key Source Files", h1))

story.append(make_table(
    ["File", "Purpose"],
    [
        ["cli/karma/syncthing.py", "SyncthingClient: REST API wrapper for device/folder management"],
        ["cli/karma/main.py", "CLI entry point: init, team, project, watch, accept, status commands"],
        ["cli/karma/packager.py", "SessionPackager: discovers and stages session files"],
        ["cli/karma/watcher.py", "SessionWatcher: watchdog-based filesystem monitoring"],
        ["cli/karma/manifest.py", "SyncManifest/SessionEntry Pydantic models"],
        ["cli/karma/config.py", "SyncConfig/SyncthingSettings: identity & credentials"],
        ["cli/karma/sync.py", "IPFS sync & pull operations, encode_project_path()"],
        ["cli/karma/worktree_discovery.py", "Discovers Claude Desktop worktree directories"],
        ["api/services/syncthing_proxy.py", "SyncthingProxy: async wrapper for FastAPI"],
        ["api/services/remote_sessions.py", "Reads remote-sessions/ dir, builds SessionMetadata"],
        ["api/routers/sync_status.py", "All /sync/* API endpoints (teams, devices, watcher, pending)"],
        ["api/db/sync_queries.py", "SQLite CRUD for teams, members, projects, events"],
        ["api/db/schema.py", "sync_teams, sync_members, sync_team_projects, sync_events tables"],
        ["frontend/src/routes/sync/+page.svelte", "Sync setup & overview page"],
        ["frontend/src/routes/team/+page.svelte", "Team listing page"],
        ["frontend/src/routes/team/[name]/+page.svelte", "Team detail page"],
        ["frontend/src/lib/components/sync/SetupWizard.svelte", "3-step Syncthing setup wizard"],
        ["frontend/src/lib/components/sync/OverviewTab.svelte", "Sync dashboard with stats, watcher, pending"],
    ],
    col_widths=[3.2*inch, 3.6*inch],
))

story.append(Spacer(1, 16))
story.append(hr())
story.append(Paragraph(
    "Generated from codebase analysis of claude-code-karma monorepo. "
    "Date: 2026-03-07.",
    ParagraphStyle("Footer", parent=body, fontSize=7, textColor=MID, alignment=1),
))

# ── Generate ───────────────────────────────────────────────────────
doc.build(story)
print(f"PDF generated: {OUTPUT}")
