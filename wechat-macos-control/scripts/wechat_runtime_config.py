#!/usr/bin/env python3
"""Runtime config for the WeChat auto-reply service."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_STORAGE_ROOT = Path(
    os.environ.get(
        "WECHAT_LOCAL_DATA_ROOT",
        str(Path.home() / "Library" / "Application Support" / "wechat-macos-control"),
    )
).expanduser()
DEFAULT_CONFIG_PATH = Path(
    os.environ.get("WECHAT_RUNTIME_CONFIG_PATH", str(DEFAULT_STORAGE_ROOT / "runtime-config.json"))
).expanduser()
PROFILE_CHOICES = ("immediate", "least-disturbance")
SEND_MODE_CHOICES = ("enter", "cmd-enter", "ctrl-enter")
SERVICE_MODE_CHOICES = ("auto-reply", "save-only")


@dataclass
class RuntimeConfig:
    profile: str = "immediate"
    mode: str = "auto-reply"
    send_mode: str = "cmd-enter"
    idle_seconds_before_send: int = 8
    context_limit: int = 12
    poll_interval_seconds: float = 2.0
    settle_seconds: float = 0.35
    reply_quiet_window_seconds: float = 1.6


def sanitize_profile(value: object) -> str:
    if isinstance(value, str) and value in PROFILE_CHOICES:
        return value
    return RuntimeConfig.profile


def sanitize_send_mode(value: object) -> str:
    if isinstance(value, str) and value in SEND_MODE_CHOICES:
        return value
    return RuntimeConfig.send_mode


def sanitize_service_mode(value: object) -> str:
    if isinstance(value, str) and value in SERVICE_MODE_CHOICES:
        return value
    return RuntimeConfig.mode


def sanitize_idle_seconds(value: object) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return RuntimeConfig.idle_seconds_before_send
    return max(parsed, 0)


def sanitize_context_limit(value: object) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return RuntimeConfig.context_limit
    return min(max(parsed, 4), 24)


def sanitize_poll_interval(value: object) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return RuntimeConfig.poll_interval_seconds
    return min(max(parsed, 1.0), 10.0)


def sanitize_settle_seconds(value: object) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return RuntimeConfig.settle_seconds
    return min(max(parsed, 0.15), 1.5)


def sanitize_reply_quiet_window(value: object) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return RuntimeConfig.reply_quiet_window_seconds
    return min(max(parsed, 0.5), 8.0)


def normalize_runtime_config(raw: dict[str, object] | None = None) -> RuntimeConfig:
    raw = raw or {}
    return RuntimeConfig(
        profile=sanitize_profile(raw.get("profile")),
        mode=sanitize_service_mode(raw.get("mode")),
        send_mode=sanitize_send_mode(raw.get("send_mode")),
        idle_seconds_before_send=sanitize_idle_seconds(raw.get("idle_seconds_before_send")),
        context_limit=sanitize_context_limit(raw.get("context_limit")),
        poll_interval_seconds=sanitize_poll_interval(raw.get("poll_interval_seconds")),
        settle_seconds=sanitize_settle_seconds(raw.get("settle_seconds")),
        reply_quiet_window_seconds=sanitize_reply_quiet_window(raw.get("reply_quiet_window_seconds")),
    )


def load_runtime_config(path: Path = DEFAULT_CONFIG_PATH) -> RuntimeConfig:
    if not path.exists():
        return RuntimeConfig()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return RuntimeConfig()
    if not isinstance(raw, dict):
        return RuntimeConfig()
    return normalize_runtime_config(raw)


def save_runtime_config(config: RuntimeConfig, path: Path = DEFAULT_CONFIG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(config), ensure_ascii=False, indent=2), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage runtime config for the WeChat auto-reply service")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("show")
    subparsers.add_parser("reset")

    parser_set = subparsers.add_parser("set")
    parser_set.add_argument("--profile", choices=PROFILE_CHOICES)
    parser_set.add_argument("--mode", choices=SERVICE_MODE_CHOICES)
    parser_set.add_argument("--send-mode", choices=SEND_MODE_CHOICES)
    parser_set.add_argument("--idle-seconds", type=int)
    parser_set.add_argument("--context-limit", type=int)
    parser_set.add_argument("--poll-interval", type=float)
    parser_set.add_argument("--settle-seconds", type=float)
    parser_set.add_argument("--reply-quiet-window", type=float)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "show":
        config = load_runtime_config()
    elif args.command == "reset":
        config = RuntimeConfig()
        save_runtime_config(config)
    elif args.command == "set":
        config = load_runtime_config()
        if args.profile is not None:
            config.profile = args.profile
        if args.mode is not None:
            config.mode = args.mode
        if args.send_mode is not None:
            config.send_mode = args.send_mode
        if args.idle_seconds is not None:
            config.idle_seconds_before_send = sanitize_idle_seconds(args.idle_seconds)
        if args.context_limit is not None:
            config.context_limit = sanitize_context_limit(args.context_limit)
        if args.poll_interval is not None:
            config.poll_interval_seconds = sanitize_poll_interval(args.poll_interval)
        if args.settle_seconds is not None:
            config.settle_seconds = sanitize_settle_seconds(args.settle_seconds)
        if args.reply_quiet_window is not None:
            config.reply_quiet_window_seconds = sanitize_reply_quiet_window(args.reply_quiet_window)
        save_runtime_config(config)
    else:  # pragma: no cover - argparse enforces this
        parser.error(f"unknown command: {args.command}")

    print(json.dumps(asdict(config), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
