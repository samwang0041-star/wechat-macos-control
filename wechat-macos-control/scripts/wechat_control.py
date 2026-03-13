#!/usr/bin/env python3
"""Minimal deterministic WeChat automation for macOS."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from wechat_message_store import DEFAULT_STORAGE_ROOT, ArchivedMessage, append_messages
from wechat_style_profile import rebuild_style_profile

WECHAT_APP = "/Applications/WeChat.app"
WECHAT_BUNDLE_ID = "com.tencent.xinWeChat"
DEFAULT_PROCESS_NAME = "WeChat"
AX_QUERY_SCRIPT = Path(__file__).with_name("wechat_ax_query.swift")
AX_ACTION_SCRIPT = Path(__file__).with_name("wechat_ax_action.swift")
RECENT_LOCAL_SENDS_PATH = Path(
    os.environ.get("WECHAT_RECENT_SENDS_PATH", str(DEFAULT_STORAGE_ROOT / "recent-local-sends.json"))
).expanduser()
RECENT_LOCAL_SEND_WINDOW_SECONDS = int(os.environ.get("WECHAT_RECENT_SEND_WINDOW_SECONDS", "600"))
RECENT_LOCAL_SEND_MAX_ITEMS = int(os.environ.get("WECHAT_RECENT_SEND_MAX_ITEMS", "200"))
RECENT_LOCAL_SEND_CONTEXT_LIMIT = int(os.environ.get("WECHAT_RECENT_SEND_CONTEXT_LIMIT", "8"))

TIME_PATTERNS = (
    re.compile(r"^\d{1,2}:\d{2}$"),
    re.compile(r"^(今天|昨天|前天)$"),
    re.compile(r"^(今天|昨天|前天)\s+\d{1,2}:\d{2}$"),
    re.compile(r"^(星期[一二三四五六日天])$"),
    re.compile(r"^(星期[一二三四五六日天]\s+\d{1,2}:\d{2})$"),
)

def run_osascript(script: str, *args: str) -> str:
    cmd = ["osascript", "-l", "AppleScript", "-"] + list(args)
    proc = subprocess.run(
        cmd,
        input=script,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        message = proc.stderr.strip() or proc.stdout.strip() or "osascript failed"
        raise RuntimeError(f"apple-script: {message}")
    return proc.stdout.strip()


def applescript_string_list(script: str, *args: str) -> list[str]:
    output = run_osascript(script, *args)
    if not output:
        return []
    return [item.strip() for item in output.split(", ") if item.strip()]


def activate() -> None:
    run_osascript('tell application "WeChat" to activate')


def normalize_text(text: str) -> str:
    return " ".join(text.split()).strip()


def is_time_like(text: str) -> bool:
    value = normalize_text(text)
    return any(pattern.match(value) for pattern in TIME_PATTERNS)


def meaningful_tail_from_raw_messages(raw_messages: list[object], limit: int = RECENT_LOCAL_SEND_CONTEXT_LIMIT) -> list[str]:
    results: list[str] = []
    for item in raw_messages:
        value = normalize_text(str(item))
        if not value or value == "消息" or is_time_like(value):
            continue
        results.append(value)
    return results[-limit:]


def load_recent_local_sends() -> list[dict[str, object]]:
    if not RECENT_LOCAL_SENDS_PATH.exists():
        return []
    try:
        payload = json.loads(RECENT_LOCAL_SENDS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []
    return payload if isinstance(payload, list) else []


def save_recent_local_sends(entries: list[dict[str, object]]) -> None:
    RECENT_LOCAL_SENDS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RECENT_LOCAL_SENDS_PATH.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def record_recent_local_send(chat_name: str, text: str, before_tail: list[str]) -> None:
    now = time.time()
    normalized = normalize_text(text)
    if not chat_name or not normalized:
        return

    kept: list[dict[str, object]] = []
    for item in load_recent_local_sends():
        try:
            sent_at = float(item.get("sent_at", 0))
        except (TypeError, ValueError):
            continue
        if now - sent_at > RECENT_LOCAL_SEND_WINDOW_SECONDS:
            continue
        kept.append(item)

    kept.append(
        {
            "id": f"{time.time_ns()}-{len(kept)}",
            "chat": chat_name,
            "text": normalized,
            "sent_at": now,
            "before_tail": before_tail[-RECENT_LOCAL_SEND_CONTEXT_LIMIT:],
        }
    )
    save_recent_local_sends(kept[-RECENT_LOCAL_SEND_MAX_ITEMS:])


def installed() -> bool:
    return Path(WECHAT_APP).exists()


def running() -> bool:
    script = f'''
tell application "System Events"
    return name of every process whose bundle identifier is "{WECHAT_BUNDLE_ID}"
end tell
'''
    return DEFAULT_PROCESS_NAME in applescript_string_list(script)


def current_windows() -> list[str]:
    script = f'''
tell application "System Events"
    tell process "{DEFAULT_PROCESS_NAME}"
        return name of windows
    end tell
end tell
'''
    return applescript_string_list(script)


def top_menu_items() -> list[str]:
    script = f'''
tell application "System Events"
    tell process "{DEFAULT_PROCESS_NAME}"
        return name of every menu bar item of menu bar 1
    end tell
end tell
'''
    return applescript_string_list(script)


def menu_items(menu_name: str) -> list[str]:
    script = f'''
on run argv
    set menuName to item 1 of argv
    tell application "System Events"
        tell process "{DEFAULT_PROCESS_NAME}"
            tell menu bar item menuName of menu bar 1
                tell menu 1
                    return name of every menu item
                end tell
            end tell
        end tell
    end tell
end run
'''
    return applescript_string_list(script.replace("\r", ""), menu_name)


def check() -> dict[str, object]:
    state: dict[str, object] = {
        "installed": installed(),
        "osascript": shutil.which("osascript") is not None,
    }

    try:
        state["running"] = running()
    except Exception as exc:  # pragma: no cover - environment-specific
        state["running"] = False
        state["running_error"] = str(exc)
        return state

    if state["running"]:
        try:
            state["windows"] = current_windows()
            state["menu_bar"] = top_menu_items()
            state["file_menu"] = menu_items("文件")
            state["edit_menu"] = menu_items("编辑")
        except Exception as exc:  # pragma: no cover - environment-specific
            state["ui_error"] = str(exc)

    return state


def snapshot() -> dict[str, object]:
    activate()
    return check()


def start_chat(target: str) -> None:
    script = f'''
on run argv
    set targetName to item 1 of argv
    set previousClipboard to the clipboard
    try
        tell application "WeChat" to activate
        delay 0.2
        set the clipboard to targetName
        tell application "System Events"
            tell process "{DEFAULT_PROCESS_NAME}"
                click menu item "发起会话" of menu 1 of menu bar item "文件" of menu bar 1
                delay 0.35
                keystroke "a" using command down
                delay 0.05
                keystroke "v" using command down
                delay 0.45
                key code 125
                delay 0.08
                key code 36
                delay 0.35
                if exists sheet 1 of window 1 then
                    if exists button "完成" of sheet 1 of window 1 then
                        click button "完成" of sheet 1 of window 1
                    end if
                end if
            end tell
        end tell
    on error errMsg number errNum
        set the clipboard to previousClipboard
        error errMsg number errNum
    end try
    set the clipboard to previousClipboard
end run
'''
    run_osascript(script, target)


def paste_text(text: str) -> None:
    activate()
    focus_compose()
    run_swift_action("set-compose-text", text)


def send_staged(mode: str) -> None:
    if mode not in {"enter", "cmd-enter", "ctrl-enter"}:
        raise ValueError("mode must be 'enter', 'cmd-enter', or 'ctrl-enter'")

    run_swift_action("send-shortcut", "--mode", mode)


def run_swift_query(command: str, *args: str) -> object:
    cmd = ["swift", str(AX_QUERY_SCRIPT), command] + list(args)
    proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        message = proc.stderr.strip() or proc.stdout.strip() or "swift query failed"
        raise RuntimeError(f"ax-query:{command}: {message}")
    output = proc.stdout.strip()
    if not output:
        return None
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return output


def run_swift_action(command: str, *args: str) -> None:
    cmd = ["swift", str(AX_ACTION_SCRIPT), command] + list(args)
    proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        message = proc.stderr.strip() or proc.stdout.strip() or "swift action failed"
        raise RuntimeError(f"ax-action:{command}: {message}")


def current_chat() -> object:
    return run_swift_query("current-chat")


def compose_text() -> object:
    return run_swift_query("compose-text")


def visible_chats(limit: int) -> object:
    return run_swift_query("visible-chats", "--limit", str(limit))


def current_messages(limit: int) -> object:
    return run_swift_query("current-messages", "--limit", str(limit))


def focus_compose() -> None:
    run_swift_action("focus-compose")


def select_visible_chat(target: str, pause: float = 0.25, timeout: float = 1.8) -> bool:
    activate()
    time.sleep(0.2)
    run_swift_action("select-visible-chat", target)
    deadline = time.time() + max(pause, timeout)
    time.sleep(min(pause, 0.35))
    while time.time() <= deadline:
        current = str(current_chat() or "").strip()
        if target in current:
            return True
        time.sleep(0.1)
    return False


def send_text(target: str, text: str, mode: str, pause: float, archive_source: str | None = None) -> None:
    try:
        before_messages = current_messages(RECENT_LOCAL_SEND_CONTEXT_LIMIT + 6)
    except Exception as exc:
        raise RuntimeError(f"ax-read: failed to read message tail before send: {exc}") from exc
    before_tail = meaningful_tail_from_raw_messages(before_messages if isinstance(before_messages, list) else [])
    try:
        current = str(current_chat() or "").strip()
    except Exception as exc:
        raise RuntimeError(f"ax-read: failed to resolve current chat before send: {exc}") from exc
    if target not in current:
        try:
            selected = select_visible_chat(target, pause=max(0.2, pause))
        except Exception as exc:
            raise RuntimeError(f"ui-chat-select: {exc}") from exc
        if not selected:
            raise RuntimeError(
                f"ui-chat-select: target chat '{target}' is not current and not selectable in the visible sidebar"
            )
    try:
        focus_compose()
    except Exception as exc:
        raise RuntimeError(f"ui-focus-compose: {exc}") from exc
    time.sleep(0.1)
    try:
        paste_text(text)
    except Exception as exc:
        raise RuntimeError(f"ui-compose-write: {exc}") from exc
    time.sleep(0.15)
    try:
        send_staged(mode)
    except Exception as exc:
        raise RuntimeError(f"ui-send-shortcut: {exc}") from exc
    try:
        record_recent_local_send(target, text, before_tail)
    except Exception as exc:
        raise RuntimeError(f"local-send-marker-write: {exc}") from exc
    if archive_source and archive_source not in {"none", "skip", "disabled"}:
        try:
            append_messages(
                [
                    ArchivedMessage(
                        chat_name=target,
                        observed_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
                        text=normalize_text(text),
                        direction="outgoing",
                        source=archive_source,
                        context=(before_tail + [normalize_text(text)])[-RECENT_LOCAL_SEND_CONTEXT_LIMIT:],
                    )
                ]
            )
            if archive_source in {"helper-send", "user-approved", "manual-observed"}:
                rebuild_style_profile()
        except Exception as exc:
            raise RuntimeError(f"archive-write-after-send: {exc}") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Operate desktop WeChat on macOS")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("check")
    subparsers.add_parser("activate")
    subparsers.add_parser("snapshot")

    parser_start = subparsers.add_parser("start-chat")
    parser_start.add_argument("name")

    parser_paste = subparsers.add_parser("paste-text")
    parser_paste.add_argument("text")

    parser_current_chat = subparsers.add_parser("current-chat")
    parser_current_chat.add_argument("--json", action="store_true")

    subparsers.add_parser("compose-text")

    parser_visible = subparsers.add_parser("visible-chats")
    parser_visible.add_argument("--limit", type=int, default=10)

    parser_messages = subparsers.add_parser("read-current-messages")
    parser_messages.add_argument("--limit", type=int, default=10)

    subparsers.add_parser("focus-compose")

    parser_select_visible = subparsers.add_parser("select-visible-chat")
    parser_select_visible.add_argument("name")
    parser_select_visible.add_argument(
        "--pause",
        type=float,
        default=0.3,
        help="Seconds to wait after selecting a visible chat",
    )

    parser_send = subparsers.add_parser("send-staged")
    parser_send.add_argument(
        "--mode",
        default="enter",
        choices=["enter", "cmd-enter"],
        help="Match the user's WeChat send shortcut",
    )

    parser_send_text = subparsers.add_parser("send-text")
    parser_send_text.add_argument("name")
    parser_send_text.add_argument("text")
    parser_send_text.add_argument(
        "--mode",
        default="enter",
        choices=["enter", "cmd-enter", "ctrl-enter"],
        help="Match the user's WeChat send shortcut",
    )
    parser_send_text.add_argument(
        "--pause",
        type=float,
        default=0.45,
        help="Seconds to wait after opening the chat before pasting text",
    )
    parser_send_text.add_argument(
        "--archive-source",
        default="helper-send",
        help="Optional local archive source tag for this confirmed outgoing message; use 'none' to skip",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.command == "check":
            print(json.dumps(check(), ensure_ascii=False, indent=2))
        elif args.command == "activate":
            activate()
        elif args.command == "snapshot":
            print(json.dumps(snapshot(), ensure_ascii=False, indent=2))
        elif args.command == "start-chat":
            start_chat(args.name)
        elif args.command == "paste-text":
            paste_text(args.text)
        elif args.command == "current-chat":
            data = current_chat()
            if args.json:
                print(json.dumps({"current_chat": data}, ensure_ascii=False, indent=2))
            else:
                print(data or "")
        elif args.command == "compose-text":
            print(compose_text() or "")
        elif args.command == "visible-chats":
            print(json.dumps(visible_chats(args.limit), ensure_ascii=False, indent=2))
        elif args.command == "read-current-messages":
            print(json.dumps(current_messages(args.limit), ensure_ascii=False, indent=2))
        elif args.command == "focus-compose":
            focus_compose()
        elif args.command == "select-visible-chat":
            if not select_visible_chat(args.name, args.pause):
                raise RuntimeError(f"ui-chat-select: failed to select visible chat: {args.name}")
        elif args.command == "send-staged":
            send_staged(args.mode)
        elif args.command == "send-text":
            send_text(args.name, args.text, args.mode, args.pause, args.archive_source)
        else:  # pragma: no cover - argparse enforces this
            parser.error(f"unknown command: {args.command}")
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
