# Settings Guide

A plain-language tour of the Settings page: what each control does, why you'd want it, and what happens when you touch it. Most of these are Claude Code settings most people never discover on their own — that's the whole point of this page.

---

## Which file am I editing?

This page edits your **user** settings file, normally `~/.claude/settings.json`. If you run more than one Claude account side by side using `CLAUDE_CONFIG_DIR`, this page only edits the account it's currently pointed at — check which one before assuming a change applied everywhere.

Before every save, karma copies your current file to `settings.json.karma-bak` and writes the new one to a temp file first, then swaps it into place atomically. If anything goes wrong mid-write, your original file is never left half-written — worst case, you're exactly where you started.

Two things this page will never touch, on purpose: `theme` (that lives in a different internal file, not settings.json) and anything that would need editing `env`, `hooks`, `apiKeyHelper`, or `permissions.additionalDirectories` — those are security-sensitive enough that a dashboard write path to them just isn't worth the risk. Edit those by hand if you need them.

## Reading the badges

- **"New sessions"** — Claude Code reads settings.json once, when a session starts. Anything with this badge won't change your *current* session; it applies the next time you start one.
- **"Default: …" and Reset** — Reset doesn't write today's default value back into your file, it deletes the key entirely. That way if Claude Code changes its own default later, you inherit the new one automatically instead of staying pinned to whatever "default" meant when you clicked Reset.

---

## Desktop App

This section isn't a Claude Code setting at all — it's karma's own native launcher, unrelated to settings.json.

**Start Karma at login** — starts both the API and frontend servers automatically when you log in, so the dashboard is just always there. It costs roughly 150–350 MB of memory in the background and almost no CPU, which is the trade you're making for never needing to click an icon first.

**Pin the launcher to the Dock** — only useful if you *don't* have autostart on; with autostart running the servers already, pin the browser-installed Karma window instead so you're not duplicating icons. Pinning briefly restarts the Dock (that's macOS, not a karma bug).

---

## General

**Session Retention** — how many days Claude Code keeps old session transcripts before deleting them. Set it to "Forever" if you don't want automatic cleanup at all.

**Extended Thinking** — turns on deeper reasoning by default for every session, instead of only when you ask for it. Slower and pricier per response, but noticeably better on hard problems. You can still toggle it per-session with Option+T regardless of this setting.

**Default Model** — the model a new session starts on, so you don't have to `/model` your way there every time. Type an alias (`sonnet`, `opus`, `haiku`, `fable`) or paste a full model ID. Leave it blank to just use your account's default.

**Update Channel** — Latest ships the newest release the moment it's out; Stable trails by about a week and skips versions with major regressions. Most people want Latest; pick Stable if you've been burned by a bad release before.

**Verbose Output** — shows full command output in the transcript instead of Claude's collapsed summary. Useful when you're debugging a command yourself and don't want the summary getting in the way.

## Input

**Spell Check** — underlines misspelled words in the prompt box as you type. It's purely visual — nothing gets auto-corrected or changed for you. This needs a spell checker (`aspell`, `hunspell`, or `ispell`) actually installed on your machine; karma checks for one and disables the toggle with an install hint if it can't find any. This is also the setting that inspired this whole page — it's easy to turn on and then wonder why nothing seems to happen, when really it's just quietly waiting on a checker that isn't installed.

**Editor Mode** — switches the prompt box to Vim keybindings (`hjkl`, text objects, `v`/`d`/`c`/`y`). Enter still submits your message even in insert mode, so you won't get stuck.

## Notifications

**Notifications** — how Claude Code tells you it's done or needs your input: a terminal bell, a native desktop notification (only works in iTerm2, Kitty, or Ghostty), both together, or nothing at all. "Auto" picks a desktop notification when your terminal supports one and stays silent otherwise — if you're not seeing anything, that's usually why.

## Git

**Commit Attribution** — turning this off removes the "Co-Authored-By: Claude" trailer from commits Claude Code makes for you. Note this is the older of two ways to control attribution — Claude Code's newer `attribution` setting can also customize or hide the pull-request text and the session link separately, but that's a more involved object-shaped setting we haven't wired up a UI for yet.

## Permissions

**Default Permission Mode** — how Claude handles tool permission requests when a session starts:

| Mode | What it does |
|------|--------------|
| Default | Prompts you the first time it wants to use each tool |
| Auto-accept Edits | Auto-approves file edits; everything else still prompts |
| Plan Mode | Read-only — Claude can look but can't change or run anything |
| Pre-approved Only | Auto-denies anything not already in your allow list below |
| Bypass All | Skips every permission check — only use this somewhere isolated |

**Allowed Tools** — the list of tools and commands granted automatically, without a prompt, regardless of mode. Add specific commands here (like `Bash(git status)`) to stop being asked about the ones you always approve anyway.

## Plugins

Each installed plugin gets its own on/off switch here. This mirrors what `/install-plugin` sets up in Claude Code — there's nothing to configure beyond enabling or disabling.

## Advanced

**Status Line Command** — a shell command that receives the session's JSON on stdin and prints whatever you want shown at the bottom of Claude Code's terminal (model name, git branch, cost so far — your call). Run `/statusline` inside Claude Code if you want it to generate a working one for you instead of writing it by hand.

**View Raw JSON** — the exact contents of your settings.json, in case you want to check something this page doesn't have a control for yet. Both this and the Status Line command have a small copy icon next to them for grabbing the text quickly.

---

## Something not here?

This page only exposes settings.json keys that are genuinely useful day-to-day and safe to expose from a dashboard. There are many more — see the [full settings reference](https://code.claude.com/docs/en/settings-reference) for everything Claude Code reads from that file.
