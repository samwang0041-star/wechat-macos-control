---
name: wechat-macos-control
description: Operate the macOS desktop WeChat client through Accessibility and AppleScript helpers. Use when the user wants Codex to activate WeChat, inspect the current window state, open a chat, paste or send text, or debug WeChat desktop automation on macOS.
---

# WeChat macOS Control

## Overview

Use this skill to control the native macOS WeChat app at `/Applications/WeChat.app` with deterministic local automation first. Prefer the bundled scripts over ad hoc AppleScript so clipboard handling, menu paths, and safety checks stay consistent.

Current runtime policy:

- auto-reply never falls back to `发起会话`
- sending is limited to the current chat or a chat already visible in the left sidebar
- if a target chat is not directly selectable in the visible sidebar, the service skips it instead of searching for the contact

Typical layout:

- Skill folder: `$CODEX_HOME/skills/wechat-macos-control`
- Runtime/data files: `$WECHAT_LOCAL_DATA_ROOT`
- Default runtime/data root if unset: `~/Library/Application Support/wechat-macos-control`

## Preconditions

- Confirm the host is macOS and WeChat is installed or running.
- Confirm Codex or the terminal already has Accessibility permission in `系统设置 -> 隐私与安全性 -> 辅助功能`.
- Assume the desktop client bundle id is `com.tencent.xinWeChat`.
- Treat message sending as high risk. Paste first; only send when the user explicitly asks.

## Quick Start

Use the bundled helpers from the skill directory:

```bash
python3 "$CODEX_HOME/skills/wechat-macos-control/scripts/wechat_control.py" check
```

Common commands:

```bash
python3 "$CODEX_HOME/skills/wechat-macos-control/scripts/wechat_control.py" activate
python3 "$CODEX_HOME/skills/wechat-macos-control/scripts/wechat_control.py" snapshot
python3 "$CODEX_HOME/skills/wechat-macos-control/scripts/wechat_control.py" current-chat
python3 "$CODEX_HOME/skills/wechat-macos-control/scripts/wechat_control.py" visible-chats --limit 5
python3 "$CODEX_HOME/skills/wechat-macos-control/scripts/wechat_control.py" select-visible-chat "张三"
python3 "$CODEX_HOME/skills/wechat-macos-control/scripts/wechat_control.py" read-current-messages --limit 8
python3 "$CODEX_HOME/skills/wechat-macos-control/scripts/wechat_control.py" focus-compose
python3 "$CODEX_HOME/skills/wechat-macos-control/scripts/wechat_control.py" start-chat "张三"
python3 "$CODEX_HOME/skills/wechat-macos-control/scripts/wechat_control.py" paste-text "你好"
python3 "$CODEX_HOME/skills/wechat-macos-control/scripts/wechat_control.py" send-text "张三" "你好" --mode enter
python3 "$CODEX_HOME/skills/wechat-macos-control/scripts/wechat_control.py" send-staged --mode enter
swift "$CODEX_HOME/skills/wechat-macos-control/scripts/wechat_ax_dump.swift" --depth 3
python3 "$CODEX_HOME/skills/wechat-macos-control/scripts/wechat_autoreply_service.py" --chat "文件传输助手" --dry-run --mock-reply "收到"
python3 "$CODEX_HOME/skills/wechat-macos-control/scripts/wechat_runtime_config.py" show
python3 "$CODEX_HOME/skills/wechat-macos-control/scripts/wechat_runtime_config.py" set --mode save-only
python3 "$CODEX_HOME/skills/wechat-macos-control/scripts/wechat_runtime_config.py" set --mode auto-reply
python3 "$CODEX_HOME/skills/wechat-macos-control/scripts/wechat_runtime_config.py" set --profile least-disturbance --idle-seconds 8
python3 "$CODEX_HOME/skills/wechat-macos-control/scripts/wechat_runtime_config.py" set --context-limit 12
python3 "$CODEX_HOME/skills/wechat-macos-control/scripts/wechat_style_profile.py" rebuild
python3 "$CODEX_HOME/skills/wechat-macos-control/scripts/wechat_style_profile.py" show
```

## Default Workflow

1. Run `check` first.
   This verifies that WeChat exists, `System Events` can see the process, and the expected menu items are available.
2. Run `snapshot` before any destructive action.
   Use it to confirm window titles and menu structure before assuming a state.
3. Prefer deterministic actions.
   Use `current-chat`, `visible-chats`, and `read-current-messages` to understand state before acting. Prefer visible-sidebar selection and `paste-text` staging over any search-based flow.
4. Send only on explicit instruction.
   Use `send-staged` only when the user asked to send, not when they merely asked to draft or prepare.
5. If UI assumptions fail, inspect the accessibility tree.
   Use `wechat_ax_dump.swift` to dump the current window tree, then adapt the next action based on the actual structure.

## Commands

### `check`

Return JSON describing whether WeChat is installed, whether the process is visible to `System Events`, the current window titles, and the top-level menu names.

### `activate`

Bring WeChat to the foreground without sending input.

### `snapshot`

Return a JSON snapshot of visible windows and important menus. Use this before selecting menu items or assuming a shortcut exists.

### `start-chat "联系人名"`

Open `文件 -> 发起会话`, paste the provided name through the clipboard, and press Return to select the first result. Use only when the target name is unambiguous.

### `current-chat`

Return the current conversation title from the focused WeChat window.

### `visible-chats`

Return the visible conversation list entries from the left sidebar.

```bash
python3 "$CODEX_HOME/skills/wechat-macos-control/scripts/wechat_control.py" visible-chats --limit 10
```

### `read-current-messages`

Return the visible message fragments from the current chat. The AX query redacts obvious token-like secrets before printing.

```bash
python3 "$CODEX_HOME/skills/wechat-macos-control/scripts/wechat_control.py" read-current-messages --limit 12
```

### `select-visible-chat "联系人名"`

Select a chat that is already visible in the left sidebar using Accessibility, without going through the `发起会话` paste flow. Prefer this over `start-chat` when the target chat is already on screen.

### `focus-compose`

Move keyboard focus into the current chat's message composer before pasting or sending text.

### `paste-text "内容"`

Paste text into the currently focused field while preserving the previous clipboard contents.

### `send-staged`

Send the staged message with either `Enter` or `Cmd+Enter`.

```bash
python3 "$CODEX_HOME/skills/wechat-macos-control/scripts/wechat_control.py" send-staged --mode enter
python3 "$CODEX_HOME/skills/wechat-macos-control/scripts/wechat_control.py" send-staged --mode cmd-enter
```

### `send-text`

Send to the current chat or to a chat already visible in the left sidebar. This command no longer falls back to `发起会话`.

```bash
python3 "$CODEX_HOME/skills/wechat-macos-control/scripts/wechat_control.py" send-text "张三" "你好" --mode enter
```

### `wechat_autoreply_service.py`

Run a guarded polling service for one or more whitelisted chats. Prefer `--dry-run` first, then remove it only after verifying the right chat names, prompt, and send shortcut.

```bash
python3 "$CODEX_HOME/skills/wechat-macos-control/scripts/wechat_autoreply_service.py" \
  --chat "文件传输助手" \
  --dry-run \
  --mock-reply "收到"
```

Default live mode uses the local `codex` CLI authenticated with your ChatGPT subscription. This path does not require `OPENAI_API_KEY`:

```bash
python3 "$CODEX_HOME/skills/wechat-macos-control/scripts/wechat_autoreply_service.py" \
  --chat "客户A" \
  --chat "客户B" \
  --backend codex \
  --codex-reasoning-effort low \
  --send-mode cmd-enter
```

To watch the currently visible sidebar chats instead of a fixed whitelist:

```bash
python3 "$CODEX_HOME/skills/wechat-macos-control/scripts/wechat_autoreply_service.py" \
  --monitor-visible \
  --visible-limit 8 \
  --backend codex \
  --send-mode cmd-enter
```

Visible-monitor guardrails:

- only scans the chats currently visible in the left sidebar
- skips `消息免打扰` chats unless `--include-muted-visible` is set
- skips `公众号/服务号`
- group chats are manual-save-only, never auto-reply
- only group chats listed in `$WECHAT_LOCAL_DATA_ROOT/group-whitelist.txt` are kept for structured archival
- selects visible chats through AX only; if a visible chat cannot be selected, the service skips it instead of searching for the contact

If you explicitly want the OpenAI API instead, switch backends:

```bash
OPENAI_API_KEY=... \
python3 "$CODEX_HOME/skills/wechat-macos-control/scripts/wechat_autoreply_service.py" \
  --chat "客户A" \
  --backend openai \
  --model "gpt-5-mini"
```

Guardrails built into the service:

- replies only for explicitly whitelisted chats
- the first poll primes state and does not answer backlog
- suspicious injection-like messages are skipped
- `--dry-run` logs the reply without sending it
- `--mock-reply` lets you test the whole control path without OpenAI

### `wechat_runtime_config.py`

Manage hot-reloadable runtime state for the watcher. The auto-reply service reads this file every poll, so you can switch behavior later without editing code.

```bash
python3 "$CODEX_HOME/skills/wechat-macos-control/scripts/wechat_runtime_config.py" show
python3 "$CODEX_HOME/skills/wechat-macos-control/scripts/wechat_runtime_config.py" set --profile immediate
python3 "$CODEX_HOME/skills/wechat-macos-control/scripts/wechat_runtime_config.py" set --profile least-disturbance --idle-seconds 8
python3 "$CODEX_HOME/skills/wechat-macos-control/scripts/wechat_runtime_config.py" set --mode save-only
python3 "$CODEX_HOME/skills/wechat-macos-control/scripts/wechat_runtime_config.py" set --mode auto-reply
python3 "$CODEX_HOME/skills/wechat-macos-control/scripts/wechat_runtime_config.py" set --send-mode cmd-enter
python3 "$CODEX_HOME/skills/wechat-macos-control/scripts/wechat_runtime_config.py" set --context-limit 12
python3 "$CODEX_HOME/skills/wechat-macos-control/scripts/wechat_runtime_config.py" reset
```

Profiles:

- `immediate`: current behavior, reply as soon as the watcher decides to send
- `least-disturbance`: when WeChat is not frontmost, defer sending until the machine has been idle for the configured number of seconds
- `mode=save-only`: keep watching and archive messages locally, but never call the model or send a reply
- `mode=auto-reply`: current live behavior, archive messages and reply when the watcher decides to send
- `context-limit`: how many meaningful recent message fragments the watcher keeps as reply context; higher values give better continuity but slightly longer prompts


Local archive:

- SQLite: `$WECHAT_LOCAL_DATA_ROOT/wechat-message-store.sqlite3`
- Per-chat export: `$WECHAT_LOCAL_DATA_ROOT/chats/<聊天名>.jsonl`
- Group whitelist: `$WECHAT_LOCAL_DATA_ROOT/group-whitelist.txt`
- Reply policy: `$WECHAT_LOCAL_DATA_ROOT/reply-policy.txt`
- Style profile: `$WECHAT_LOCAL_DATA_ROOT/style-profile.json`

The watcher loads `reply-policy.txt` by default and will pick up local edits on the next poll cycle.
It also reads `style-profile.json` to imitate confirmed local writing habits; this file is rebuilt from trusted outgoing samples stored locally.
Trusted style samples come from high-confidence manual sends observed while you type in WeChat, plus messages you explicitly asked the helper to send.

### `wechat_ax_dump.swift`

Dump the current WeChat accessibility tree for debugging.

```bash
swift "$CODEX_HOME/skills/wechat-macos-control/scripts/wechat_ax_dump.swift" --depth 2
swift "$CODEX_HOME/skills/wechat-macos-control/scripts/wechat_ax_dump.swift" --depth 4 --all-windows
```

Use it when a menu item moved, a text field is not where the helper expected, or WeChat updated its UI.

## Safety Rules

- Do not send messages unless the user explicitly asked to send.
- If a contact name may match multiple people or groups, stop and ask.
- Do not automate file sends, payments, or destructive account actions with this skill's default workflow.
- Message-reading commands may surface sensitive content. Keep them scoped to the smallest useful limit and rely on the built-in redaction rather than echoing secrets verbatim.
- Do not run `wechat_autoreply_service.py` against all contacts. Limit it to a small whitelist of clearly named chats.
- If the user wants message reading or richer extraction, use `snapshot` and `wechat_ax_dump.swift` first, then add OCR or screenshot-based inspection only if AX data is insufficient.
