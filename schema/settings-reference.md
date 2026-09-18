## Claude Code settings reference (trimmed)

Curated subset of the live settings reference, trimmed to only the keys in `schema/watched-keys.json` -- the settings karma's Settings page actually reads or writes. Kept in sync by `.github/workflows/schema-drift.yml`.

| Key                                                                                             | Description                                                                                                                                                                                                                 | Topic                              | Scope                   |
| :---------------------------------------------------------------------------------------------- | :-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :--------------------------------- | :---------------------- |
| [`cleanupPeriodDays`](#cleanupperioddays)                                                       | Choose how many days Claude Code keeps [transcripts](/docs/en/data-usage#data-retention) before deleting them                                                                                                                    | Privacy and telemetry              | Any file                |
| [`permissions`](#permissions)                                                                   | Set allow, ask, and deny rules and the starting [permission mode](/docs/en/permission-modes)                                                                                                                                     | Permission settings                | Any file                |
| [`statusLine`](#statusline)                                                                     | Run your own command to render a [status line](/docs/en/statusline) below the prompt                                                                                                                                             | Interface and terminal             | Any file                |
| [`enabledPlugins`](#enabledplugins)                                                             | Turn individual [plugins](/docs/en/plugins) on or off per scope                                                                                                                                                                  | Plugins and skills                 | Any file                |
| [`alwaysThinkingEnabled`](#alwaysthinkingenabled)                                               | Turn [extended thinking](/docs/en/model-config#extended-thinking) off for every session                                                                                                                                          | Model and responses                | Any file                |
| [`spellcheck`](#spellcheck)                                                                     | Underline misspelled words in the prompt input with a [spell checker](/docs/en/interactive-mode#check-spelling-as-you-type) you install                                                                                          | Interface and terminal             | User or managed         |
| [`preferredNotifChannel`](#preferrednotifchannel)                                               | Choose a [terminal bell or desktop notification](/docs/en/terminal-config#get-a-terminal-bell-or-notification) for task completion                                                                                               | Remote, desktop, and notifications | Any file                |
| [`editorMode`](#editormode)                                                                     | Use [vim key bindings](/docs/en/interactive-mode#vim-editor-mode) in the input prompt                                                                                                                                            | Interface and terminal             | Any file                |
| [`includeCoAuthoredBy`](#includecoauthoredby)                                                   | Deprecated; use `attribution` to hide or change commit and PR attribution                                                                                                                                                   | Git and attribution                | Any file                |
| [`model`](#model)                                                                               | Change the [model](/docs/en/model-config#set-a-default-model-for-new-sessions) Claude Code starts with                                                                                                                           | Model and responses                | Any file                |
| [`autoUpdatesChannel`](#autoupdateschannel)                                                     | Follow the stable [release channel](/docs/en/setup#configure-release-channel) instead of latest                                                                                                                                  | Updates and versioning             | Any file                |
| [`verbose`](#verbose)                                                                           | Show [full tool output](/docs/en/cli-reference#cli-flags) instead of truncated summaries; `viewMode` takes precedence when both are set                                                                                          | Interface and terminal             | Any file                |

### `cleanupPeriodDays`

Set how many days Claude Code keeps [session transcripts and other application data](/docs/en/claude-directory#cleaned-up-automatically) before deleting them. Claude Code runs the deletion as a background sweep after a session starts, as long as it can safely determine the retention period.

* **Scope**: [`Any file`](#scopes)
* **Type**: number of days, a whole number, minimum `1`
* **Default**: `30`

```json settings.json theme={null}
{
  "cleanupPeriodDays": 20
}
```

Setting `0` fails validation, so pick a large value such as `3650` for long retention. To stop Claude Code from writing transcripts at all, see [Plaintext storage](/docs/en/claude-directory#plaintext-storage).

### `permissions`

Control which tools Claude can use without asking, which ones always prompt, and which ones are blocked, and set the [permission mode](/docs/en/permission-modes) a session starts in. Every `permissions.*` key below nests under this object.

* **Scope**: [`Any file`](#scopes)
* **Type**: object with `allow`, `ask`, `deny`, `additionalDirectories`, `defaultMode`, `disableBypassPermissionsMode`, and `disableAutoMode`
* **Default**: unset

This example approves `npm run` commands without asking, prompts before `git push`, blocks reads of `.env`, and starts sessions in `acceptEdits`:

```json settings.json theme={null}
{
  "permissions": {
    "allow": ["Bash(npm run *)"],
    "ask": ["Bash(git push *)"],
    "deny": ["Read(./.env)"],
    "defaultMode": "acceptEdits"
  }
}
```

The three rule arrays share one syntax; see [Permission rule syntax](#permission-rule-syntax) under `permissions.allow`. For how permission rules from different files combine, see [how permission rules merge across scopes](/docs/en/permissions#settings-precedence); for how settings keys in general combine, see [Settings precedence](/docs/en/settings#settings-precedence) on the settings guide.

### `statusLine`

Run your own command to render a [status line](/docs/en/statusline) below the prompt with context such as the model, cost, or git branch. Optional fields adjust spacing, add periodic re-runs, and hide the built-in vim mode indicator when your script renders `vim.mode` itself.

* **Scope**: [`Any file`](#scopes). When [`allowManagedHooksOnly`](#allowmanagedhooksonly) is on, or [`disableAllHooks`](#disableallhooks) is set outside managed settings, only the managed settings value runs.
* **Type**: object with `type` set to `"command"` and a `command` string, plus optional `padding` as a number of characters, `refreshInterval` as a number of seconds, minimum `1`, and `hideVimModeIndicator` as a Boolean
* **Default**: unset, so no status line

This example prints the model name and context usage, and adds two characters of horizontal spacing:

```json settings.json theme={null}
{
  "statusLine": {
    "type": "command",
    "command": "jq -r '\"[\\(.model.display_name)] \\(.context_window.used_percentage // 0)% context\"'",
    "padding": 2
  }
}
```

The example needs [`jq`](https://jqlang.org/) installed and runs in a shell. For PowerShell and Git Bash equivalents, see [Windows configuration](/docs/en/statusline#windows-configuration); for the full setup, see [Manually configure a status line](/docs/en/statusline#manually-configure-a-status-line).

### `enabledPlugins`

Turn individual [plugins](/docs/en/plugins) on or off, keyed by `plugin-name@marketplace-name`. A plugin with no entry at any scope falls back to its [`defaultEnabled`](/docs/en/plugins-reference#default-enablement) value. When you enable or disable a plugin with `/plugin` or `claude plugin enable`, Claude Code writes this key for you.

* **Scope**: [`Any file`](#scopes)
* **Type**: object mapping `plugin-name@marketplace-name` to a Boolean
* **Default**: unset, so each plugin follows its `defaultEnabled` value

This example enables two plugins from the `team-tools` marketplace and disables one from `personal`:

```json settings.json theme={null}
{
  "enabledPlugins": {
    "code-formatter@team-tools": true,
    "deployment-tools@team-tools": true,
    "experimental-features@personal": false
  }
}
```

Each scope serves a different purpose:

* **User settings**: your personal plugin preferences
* **Project settings**: plugins shared with everyone in the repository
* **Local settings**: per-machine overrides, gitignored when Claude Code saves a setting there
* **Managed settings**: organization-wide policy. A plugin set to `false` here is blocked from installation at every scope and hidden from the marketplace

Project settings take precedence over user settings, so setting a plugin to `false` in `~/.claude/settings.json` doesn't disable a plugin that the project's `.claude/settings.json` enables. To opt out of a project-enabled plugin on your machine, set it to `false` in `.claude/settings.local.json` instead. Plugins force-enabled by managed settings can't be disabled this way, since managed settings override local settings.

Enabling a plugin from an external source such as a GitHub repository or npm package in a project's `.claude/settings.json` doesn't install it for other people. On every path that loads plugins, Claude Code reports the plugin as not installed until each user [installs it themselves](/docs/en/discover-plugins#configure-team-marketplaces).

### `alwaysThinkingEnabled`

Turn [extended thinking](/docs/en/model-config#extended-thinking) off for every session by setting this to `false`. Thinking is on by default, so `true` changes nothing. Most people set this through `/config` rather than by editing the file.

On models that always think, such as Fable 5, `false` has no effect. On [third-party providers](/docs/en/third-party-integrations) Claude Code omits the `thinking` parameter instead of turning thinking off, so adaptive-reasoning models may still think.

* **Scope**: [`Any file`](#scopes)
* **Type**: Boolean
  * `true`: no effect; thinking is already on
  * `false`: Claude Code turns extended thinking off for every session
* **Default**: unset, so thinking is on for models that support it
* **Per-session overrides**: [`MAX_THINKING_TOKENS`](/docs/en/env-vars) takes precedence over this key for one session: `0` turns thinking off, under the same model and provider limits as `false`, and a positive value turns thinking on even when this key is `false`. On adaptive-reasoning models the number itself is ignored

```json settings.json theme={null}
{
  "alwaysThinkingEnabled": false
}
```

### `spellcheck`

Underline misspelled words in the prompt input as you type, using a spell checker you install. Claude Code checks only the text in the input box. [Check spelling as you type](/docs/en/interactive-mode#check-spelling-as-you-type) covers installing aspell, hunspell, or ispell and what the checker covers. Requires Claude Code v2.1.235 or later.

* **Scope**: [`User or managed`](#scopes). The block from the highest tier that sets it applies as a whole.
* **Type**: object with `enabled` (Boolean), `checker` (`"aspell"`, `"hunspell"`, `"ispell"`, or `"auto"`), `language` (string, passed to the checker as its dictionary name), and `color` (string, a terminal color name, `#rrggbb`, `rgb(r,g,b)`, `ansi256(n)`, or `ansi:<name>`)
* **Default**: unset, so spell checking is off; `checker` defaults to `"auto"`, the first of the three found on `PATH`; `language` defaults to the checker's own dictionary; `color` defaults to the theme's error color

```json settings.json theme={null}
{
  "spellcheck": { "enabled": true, "language": "en_GB" }
}
```

### `preferredNotifChannel`

Choose how Claude Code notifies you when a task completes or a permission prompt is waiting. Appears in `/config` as **Local notifications**.

* **Scope**: [`Any file`](#scopes). Claude Code also reads a value left in `~/.claude.json` by older versions.
* **Type**: string, one of:
  * `"auto"`: Claude Code sends a desktop notification in iTerm2, Ghostty, and Kitty, rings the bell in Terminal.app only when its audible bell is off, and does nothing elsewhere
  * `"terminal_bell"`: Claude Code rings the bell character in any terminal
  * `"iterm2"`: Claude Code sends an iTerm2 desktop notification
  * `"iterm2_with_bell"`: Claude Code sends an iTerm2 desktop notification and rings the bell
  * `"kitty"`: Claude Code sends a Kitty desktop notification
  * `"ghostty"`: Claude Code sends a Ghostty desktop notification
  * `"notifications_disabled"`: Claude Code sends no notification
* **Default**: `"auto"`

```json settings.json theme={null}
{
  "preferredNotifChannel": "terminal_bell"
}
```

With `"auto"`, Claude Code sends a desktop notification in iTerm2, Ghostty, and Kitty. In Terminal.app it rings the bell character only when you have turned Terminal's audible bell off, and in other terminals it does nothing. Set `"terminal_bell"` to ring the bell character in any terminal. See [Get a terminal bell or notification](/docs/en/terminal-config#get-a-terminal-bell-or-notification).

### `editorMode`

Choose the key binding mode for the input prompt.

* **Scope**: [`Any file`](#scopes)
* **Type**: string, one of:
  * `"normal"`: standard key bindings in the prompt input
  * `"vim"`: vim-style editing with NORMAL, INSERT, and VISUAL modes
* **Default**: `"normal"`

```json settings.json theme={null}
{
  "editorMode": "vim"
}
```

Appears in `/config` as **Editor mode**, which writes this key to user settings.

### `includeCoAuthoredBy`

<Warning>
  Deprecated since v2.0.62, when [`attribution`](#attribution) replaced it. Claude Code still reads it, but new configurations should set `attribution`.
</Warning>

Use [`attribution`](#attribution) instead, which replaces this key and lets you change or hide the commit trailer, the pull request text, and the session link separately. Claude Code still honors `includeCoAuthoredBy: false` from settings files that predate `attribution`, but ignores it once you set `attribution.commit` or `attribution.pr`.

* **Scope**: [`Any file`](#scopes)
* **Type**: Boolean
  * `true`: the same as unset; Claude Code adds the commit trailer and the pull request attribution text
  * `false`: Claude Code omits both the commit trailer and the pull request attribution text, unless `attribution` sets `commit` or `pr`, in which case the [`attribution`](#attribution) rules apply
* **Default**: `true`

```json settings.json theme={null}
{
  "includeCoAuthoredBy": false
}
```

To hide all attribution today, set [`attribution.commit`](#attribution-commit) and [`attribution.pr`](#attribution-pr) to empty strings and [`attribution.sessionUrl`](#attribution-sessionurl) to `false`.

### `model`

Set the model every new session uses, so you don't have to pick one with `/model` each time. Setting it here doesn't stop you from switching mid-session. If your admin set an [organization default model](/docs/en/model-config#organization-default-model) to override user selection, you get that model even when you set this key in user, project, or local settings.

* **Scope**: [`Any file`](#scopes)
* **Type**: string, a model alias or full model ID
* **Default**: unset, so Claude Code uses your account's default model
* **Per-session overrides**: `--model` takes precedence over [`ANTHROPIC_MODEL`](/docs/en/env-vars), and both take precedence over this key for one session, including over a managed `model`; an [`availableModels`](#availablemodels) list still applies to the pick

```json settings.json theme={null}
{
  "model": "claude-sonnet-5"
}
```

A value here outranks [`ANTHROPIC_DEFAULT_MODEL`](/docs/en/model-config#set-a-default-model-for-new-sessions), which Claude Code uses only when nothing else selects a model.

### `autoUpdatesChannel`

Choose which [release channel](/docs/en/setup#configure-release-channel) background auto-updates and `claude update` follow. Set `"stable"` for a version that is typically about one week old and skips releases with major regressions, or `"latest"` for the most recent release.

* **Scope**: [`Any file`](#scopes). Set it in managed settings to enforce one channel across your organization.
* **Type**: string, one of:
  * `"latest"`: updates follow the most recent release
  * `"stable"`: updates follow a version that is typically about one week old and skips releases with major regressions
* **Default**: unset, so Claude Code follows `"latest"`

```json settings.json theme={null}
{
  "autoUpdatesChannel": "stable"
}
```

Claude Code writes `"stable"` to your user settings when you pick it under **Auto-update channel** in `/config`, and removes the key when you switch back to latest there. `claude install stable` and `claude install latest` also save the channel you name. Switching from `"latest"` to `"stable"` in `/config` asks whether to allow a downgrade or stay on your current version; staying sets [`minimumVersion`](#minimumversion). Homebrew installs ignore this key: the `claude-code` cask tracks stable and `claude-code@latest` tracks latest, and `claude update` defers to `brew upgrade`. To turn auto-updates off entirely, set [`DISABLE_AUTOUPDATER`](/docs/en/setup#disable-auto-updates) in `env`.

### `verbose`

By default, the transcript collapses each tool call to a short summary, such as the command Claude ran and a line count of its output, and you press `Ctrl+O` to switch the whole transcript to the expanded view when you want the details. Set this key to `true` to show every tool call's full input and output inline as it happens, which is useful when you're debugging a hook, an MCP server, or a long shell command. Appears in `/config` as **Verbose output**.

* **Scope**: [`Any file`](#scopes). A value in `~/.claude.json` from an older version applies when no settings file sets it.
* **Type**: Boolean
  * `true`: you see full tool output
  * `false`: you see truncated summaries of tool output
* **Default**: `false`
* **Per-session overrides**: [`--verbose`](/docs/en/cli-reference#cli-flags) takes precedence over this key for one session

```json settings.json theme={null}
{
  "verbose": true
}
```

A [`viewMode`](#viewmode) value or a sticky `/focus` selection overrides this key every session.

