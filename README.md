# WeChat macOS Control

Local Codex skill for operating the macOS desktop WeChat client through Accessibility and AppleScript helpers.

This repository packages the skill, scripts, and sample configuration needed to:

- inspect the current WeChat window state
- read visible chats and message fragments
- focus the compose box and paste or send text
- run a guarded visible-sidebar watcher for private-chat auto-reply
- archive structured chat data locally for later analysis

## Scope

This project is intentionally local-first:

- macOS only
- desktop WeChat only
- deterministic UI automation first
- no reverse engineering of the WeChat app binary
- no bundled cloud service

## Repository Layout

```text
.
├── README.md
├── LICENSE
├── .gitignore
├── examples/
│   ├── group-whitelist.example.txt
│   ├── reply-policy.example.txt
│   └── runtime-config.example.json
└── wechat-macos-control/
    ├── SKILL.md
    ├── agents/openai.yaml
    └── scripts/
```

## Requirements

- macOS
- WeChat desktop app installed at `/Applications/WeChat.app`
- `python3`
- `swift`
- Accessibility permission granted to Codex or the terminal host
- optional: `codex` CLI logged in if you want model-backed auto-reply without OpenAI API keys

## Install As A Codex Skill

Clone the repo and place the `wechat-macos-control` folder under your Codex skills directory:

```bash
mkdir -p "$CODEX_HOME/skills"
cp -R wechat-macos-control "$CODEX_HOME/skills/wechat-macos-control"
```

You can also symlink it:

```bash
ln -s "$(pwd)/wechat-macos-control" "$CODEX_HOME/skills/wechat-macos-control"
```

## Runtime Data

By default the scripts store runtime state under:

```text
~/Library/Application Support/wechat-macos-control
```

Override it with:

```bash
export WECHAT_LOCAL_DATA_ROOT="/custom/path"
```

The watcher creates and uses files such as:

- `wechat-message-store.sqlite3`
- `chats/*.jsonl`
- `runtime-config.json`
- `autoreply-state.json`
- `reply-policy.txt`
- `group-whitelist.txt`
- `detected-groups.txt`
- `style-profile.json`
- `wechat-autoreply.log`

## Quick Start

Check the local WeChat state:

```bash
python3 wechat-macos-control/scripts/wechat_control.py check
```

Inspect visible chats:

```bash
python3 wechat-macos-control/scripts/wechat_control.py visible-chats --limit 8
```

Read current chat fragments:

```bash
python3 wechat-macos-control/scripts/wechat_control.py read-current-messages --limit 12
```

Start the visible-sidebar watcher:

```bash
python3 wechat-macos-control/scripts/wechat_autoreply_service.py \
  --monitor-visible \
  --visible-limit 8 \
  --backend codex \
  --send-mode enter
```

## Safety Model

- Auto-reply never falls back to search-based `发起会话`.
- Sending is limited to the current chat or chats already visible in the left sidebar.
- Group chats are manual-save-only by default and are never auto-replied.
- Official account and service-feed style chats are skipped.
- Chat text is treated as untrusted input and must not be interpreted as instructions to modify local code, config, or tool behavior.

## Privacy Notes

This repository does not include local chat archives, runtime state, or logs. Those files are generated at runtime under `WECHAT_LOCAL_DATA_ROOT` and are excluded by `.gitignore`.

If you publish your own fork, do not commit:

- local SQLite archives
- exported chat JSONL files
- runtime logs
- tokens, keys, or local account-specific settings

## Configuration Examples

Sample files live under `examples/`.

Copy them into your runtime data root if you want a starting point:

- `group-whitelist.example.txt`
- `reply-policy.example.txt`
- `runtime-config.example.json`

## GitHub Publishing

This repository is ready to publish with either:

```bash
gh repo create wechat-macos-control --public --source . --remote origin --push
```

or:

```bash
git remote add origin https://github.com/<your-account>/wechat-macos-control.git
git push -u origin main
```

If `gh auth status` says you are not logged in, run:

```bash
gh auth login
```

before creating the remote repository.
