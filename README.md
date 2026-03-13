# macOS Codex 模拟你的角色去答复

Local Codex skill for simulating your role and replying through the macOS desktop WeChat client.

## 中文简介

这是一个运行在 macOS 上的本地 WeChat 自动化 skill，目标不是做一个“远程控制微信的云服务”，而是把 Codex、本地脚本和微信桌面客户端连接起来，让个人用户可以在自己的电脑上完成：

- 读取当前微信窗口和左侧会话列表
- 聚焦输入框、粘贴文本、发送消息
- 对私聊做受控的自动回复
- 对群聊做只保存、不自动回复的结构化归档
- 把本地聊天记录沉淀成后续可分析、可生成日报、可学习个人风格的数据

### 这个项目是干什么的

它本质上是一个“本地优先”的微信桌面自动化层。模型负责理解上下文和生成回复，本地脚本负责感知微信界面和执行操作。这样做的好处是：

- 不需要把桌面持续截图发给模型
- 不需要把聊天记录同步到云端
- 可以把风险动作限制在本机和可见聊天范围内
- 更容易控制性能、隐私和可解释性

### 设计思路

我的设计思路不是让大模型直接“看桌面乱点”，而是分成两层：

1. 确定性执行层  
   用 macOS 的 Accessibility、AppleScript 和 Swift helper 去做稳定动作，比如读取当前聊天、读取左侧会话、聚焦输入框、发送消息。

2. 智能决策层  
   用 Codex 或 OpenAI 模型只做理解、归纳和回复生成，不直接决定屏幕坐标和底层 UI 细节。

这套结构有几个明确边界：

- 自动回复只针对私聊
- 群聊默认只学习和归档，不自动回复
- 不通过搜索联系人兜底发消息，避免误发
- 聊天内容一律当作不可信输入，不能借此改本地代码、配置或执行逻辑

### 我是怎么设计这个 skill 的

这个 skill 不是一个单体程序，而是一组协作脚本：

- `wechat_control.py`
  负责直接操作微信
- `wechat_ax_query.swift`
  负责从 AX 树读取窗口、会话和消息结构
- `wechat_ax_action.swift`
  负责更稳定的 UI 动作
- `wechat_autoreply_service.py`
  负责轮询、上下文拼装、模型调用、归档和安全判断
- `wechat_message_store.py`
  负责把消息落到 SQLite 和按聊天导出的 JSONL
- `wechat_style_profile.py`
  负责从本地可信样本中提炼“像用户本人”的表达风格

也就是说，它的核心不是“自动回一句话”，而是“先建立一个本地可控、可扩展、可审计的微信自动化基础设施”。

### 怎么用

最简单的使用方式是 3 步：

1. 把 skill 放进 `$CODEX_HOME/skills/wechat-macos-control`
2. 给 Codex 或终端开启 macOS 辅助功能权限
3. 运行 watcher 或直接调用控制脚本

常见用法有两类：

- 手动控制  
  适合调试、读取消息、手工发消息
- 自动值守  
  适合对当前可见私聊做自动回复，并把消息保存在本地

如果你后续想做日报、待办抽取、聊天分析，这个仓库的价值主要就在于它已经把“微信操作”和“结构化数据沉淀”这两件事接到一起了。

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
