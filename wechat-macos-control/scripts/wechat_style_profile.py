#!/usr/bin/env python3
"""Build and load a local chat style profile."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from wechat_message_store import (
    DEFAULT_DB_PATH,
    DEFAULT_STORAGE_ROOT,
    fetch_recent_messages,
    fetch_top_chat_names,
)

DEFAULT_STYLE_PROFILE_PATH = DEFAULT_STORAGE_ROOT / "style-profile.json"
TRUSTED_STYLE_SOURCES = {"helper-send", "user-approved", "manual-observed"}
PUNCTUATION_MARKERS = ("。", "！", "？", "?", "~", "～")
STYLE_MARKERS = (
    "嗯",
    "哈哈",
    "好的",
    "行",
    "可以",
    "我先",
    "看下",
    "稍后",
    "晚点",
    "收到",
    "方便",
    "不方便",
)
EMOJI_LIKE_PATTERN = re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]")


@dataclass
class StyleProfile:
    generated_at: str
    trusted_outgoing_count: int
    global_style: dict[str, Any]
    by_chat: dict[str, dict[str, Any]]
    notes: list[str]


def average_length_bucket(avg_length: float) -> str:
    if avg_length <= 0:
        return "未知"
    if avg_length < 10:
        return "短句为主"
    if avg_length < 22:
        return "中短句为主"
    if avg_length < 40:
        return "中等长度"
    return "偏长句"


def unique_recent_examples(texts: list[str], limit: int) -> list[str]:
    results: list[str] = []
    seen = set()
    for text in reversed(texts):
        value = str(text).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        results.append(value)
        if len(results) >= limit:
            break
    return list(reversed(results))


def summarize_texts(texts: list[str]) -> dict[str, Any]:
    normalized = [str(text).strip() for text in texts if str(text).strip()]
    if not normalized:
        return {
            "message_count": 0,
            "length_style": "未知",
            "avg_length": 0,
            "top_punctuation": [],
            "common_markers": [],
            "emoji_ratio": 0.0,
            "recent_examples": [],
        }

    punctuation_counter: Counter[str] = Counter()
    marker_counter: Counter[str] = Counter()
    emoji_messages = 0

    for text in normalized:
        if EMOJI_LIKE_PATTERN.search(text):
            emoji_messages += 1
        for marker in PUNCTUATION_MARKERS:
            if marker in text:
                punctuation_counter[marker] += text.count(marker)
        for marker in STYLE_MARKERS:
            if marker in text:
                marker_counter[marker] += 1

    avg_length = round(sum(len(text) for text in normalized) / len(normalized), 1)
    return {
        "message_count": len(normalized),
        "length_style": average_length_bucket(avg_length),
        "avg_length": avg_length,
        "top_punctuation": [item for item, _ in punctuation_counter.most_common(4)],
        "common_markers": [item for item, _ in marker_counter.most_common(6)],
        "emoji_ratio": round(emoji_messages / len(normalized), 2),
        "recent_examples": unique_recent_examples(normalized, 4),
    }


def trusted_outgoing_texts(chat_name: str | None = None, *, limit: int = 200) -> list[str]:
    messages = fetch_recent_messages(
        chat_name=chat_name,
        limit=limit,
        directions=["outgoing"],
        exclude_sources=["auto-reply"],
        db_path=DEFAULT_DB_PATH,
    )
    return [
        message.text
        for message in messages
        if message.source in TRUSTED_STYLE_SOURCES and message.text.strip()
    ]


def rebuild_style_profile(
    *,
    profile_path: Path = DEFAULT_STYLE_PROFILE_PATH,
    per_chat_limit: int = 80,
    chat_count_limit: int = 20,
) -> StyleProfile:
    global_texts = trusted_outgoing_texts(limit=300)
    by_chat: dict[str, dict[str, Any]] = {}

    for chat_name in fetch_top_chat_names(
        directions=["outgoing"],
        exclude_sources=["auto-reply"],
        limit=chat_count_limit,
        db_path=DEFAULT_DB_PATH,
    ):
        texts = trusted_outgoing_texts(chat_name, limit=per_chat_limit)
        if texts:
            by_chat[chat_name] = summarize_texts(texts)

    notes: list[str] = []
    if not global_texts:
        notes.append("当前缺少可信的本人消息样本；只有用户明确发送或后续补充样本后，风格学习才会变准。")

    profile = StyleProfile(
        generated_at=datetime.now().isoformat(timespec="seconds"),
        trusted_outgoing_count=len(global_texts),
        global_style=summarize_texts(global_texts),
        by_chat=by_chat,
        notes=notes,
    )
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(json.dumps(asdict(profile), ensure_ascii=False, indent=2), encoding="utf-8")
    return profile


def load_style_profile(profile_path: Path = DEFAULT_STYLE_PROFILE_PATH) -> StyleProfile:
    if not profile_path.exists():
        return rebuild_style_profile(profile_path=profile_path)
    try:
        raw = json.loads(profile_path.read_text(encoding="utf-8"))
    except Exception:
        return rebuild_style_profile(profile_path=profile_path)

    return StyleProfile(
        generated_at=str(raw.get("generated_at", "")),
        trusted_outgoing_count=int(raw.get("trusted_outgoing_count", 0)),
        global_style=raw.get("global_style", {}) if isinstance(raw.get("global_style"), dict) else {},
        by_chat=raw.get("by_chat", {}) if isinstance(raw.get("by_chat"), dict) else {},
        notes=[str(item) for item in raw.get("notes", []) if str(item).strip()],
    )


def ensure_style_profile(
    profile_path: Path = DEFAULT_STYLE_PROFILE_PATH,
    db_path: Path = DEFAULT_DB_PATH,
) -> StyleProfile:
    if not profile_path.exists():
        return rebuild_style_profile(profile_path=profile_path)
    if db_path.exists():
        try:
            if db_path.stat().st_mtime > profile_path.stat().st_mtime:
                return rebuild_style_profile(profile_path=profile_path)
        except OSError:
            return rebuild_style_profile(profile_path=profile_path)
    return load_style_profile(profile_path)


def build_style_guidance(profile: StyleProfile, chat_name: str) -> str:
    sections: list[str] = []
    global_style = profile.global_style or {}

    if profile.trusted_outgoing_count > 0:
        markers = "、".join(global_style.get("common_markers", [])[:4]) or "无明显口头禅"
        punctuation = "、".join(global_style.get("top_punctuation", [])[:3]) or "无明显标点偏好"
        sections.append(
            "用户全局表达习惯:\n"
            f"- {global_style.get('length_style', '未知')}，平均长度约 {global_style.get('avg_length', 0)} 字\n"
            f"- 常见口头习惯: {markers}\n"
            f"- 常用标点: {punctuation}"
        )

    chat_style = profile.by_chat.get(chat_name, {})
    if chat_style:
        examples = "\n".join(f"- {item}" for item in chat_style.get("recent_examples", [])[:4])
        sections.append(
            "当前聊天里用户已确认本人表达样本:\n"
            f"{examples}"
        )

    if profile.notes:
        sections.append("风格学习备注:\n" + "\n".join(f"- {item}" for item in profile.notes))

    return "\n\n".join(section for section in sections if section.strip())


def main() -> int:
    parser = argparse.ArgumentParser(description="Build or show the local WeChat style profile")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("show")
    subparsers.add_parser("rebuild")
    args = parser.parse_args()

    if args.command == "show":
        profile = load_style_profile()
    else:
        profile = rebuild_style_profile()

    print(json.dumps(asdict(profile), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
