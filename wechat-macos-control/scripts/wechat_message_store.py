#!/usr/bin/env python3
"""Local message archive for the WeChat watcher."""

from __future__ import annotations

import json
import os
import re
import sqlite3
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

DEFAULT_STORAGE_ROOT = Path(
    os.environ.get(
        "WECHAT_LOCAL_DATA_ROOT",
        str(Path.home() / "Library" / "Application Support" / "wechat-macos-control"),
    )
).expanduser()
DEFAULT_DB_PATH = DEFAULT_STORAGE_ROOT / "wechat-message-store.sqlite3"
DEFAULT_EXPORT_DIR = DEFAULT_STORAGE_ROOT / "chats"

FILENAME_UNSAFE_PATTERN = re.compile(r'[\\/:*?"<>|]+')


@dataclass
class ArchivedMessage:
    chat_name: str
    observed_at: str
    text: str
    direction: str = "unknown"
    source: str = "watcher"
    message_time_text: str = ""
    context: list[str] = field(default_factory=list)


def safe_chat_filename(chat_name: str) -> str:
    value = FILENAME_UNSAFE_PATTERN.sub("_", chat_name).strip()
    return value or "untitled-chat"


def connect(db_path: Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    ensure_schema(conn)
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_name TEXT NOT NULL,
            observed_at TEXT NOT NULL,
            text TEXT NOT NULL,
            direction TEXT NOT NULL,
            source TEXT NOT NULL,
            message_time_text TEXT NOT NULL DEFAULT '',
            context_json TEXT NOT NULL DEFAULT '[]'
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_messages_chat_observed ON messages (chat_name, observed_at)"
    )
    conn.commit()


def row_to_archived_message(row: sqlite3.Row | tuple[object, ...]) -> ArchivedMessage:
    if isinstance(row, sqlite3.Row):
        payload = dict(row)
    else:
        payload = {
            "chat_name": row[0],
            "observed_at": row[1],
            "text": row[2],
            "direction": row[3],
            "source": row[4],
            "message_time_text": row[5],
            "context_json": row[6],
        }

    try:
        context = json.loads(payload.get("context_json", "[]"))
    except Exception:
        context = []
    if not isinstance(context, list):
        context = []

    return ArchivedMessage(
        chat_name=str(payload.get("chat_name", "")),
        observed_at=str(payload.get("observed_at", "")),
        text=str(payload.get("text", "")),
        direction=str(payload.get("direction", "unknown")),
        source=str(payload.get("source", "watcher")),
        message_time_text=str(payload.get("message_time_text", "")),
        context=[str(item) for item in context if str(item).strip()],
    )


def _build_in_clause(values: Iterable[str]) -> tuple[str, list[str]]:
    items = [str(value) for value in values if str(value)]
    if not items:
        return "", []
    placeholders = ", ".join("?" for _ in items)
    return f"({placeholders})", items


def fetch_recent_messages(
    *,
    chat_name: str | None = None,
    limit: int = 20,
    directions: list[str] | None = None,
    exclude_sources: list[str] | None = None,
    db_path: Path = DEFAULT_DB_PATH,
) -> list[ArchivedMessage]:
    conn = connect(db_path)
    conn.row_factory = sqlite3.Row
    clauses = ["1=1"]
    params: list[object] = []

    if chat_name:
        clauses.append("chat_name = ?")
        params.append(chat_name)

    in_clause, direction_values = _build_in_clause(directions or [])
    if in_clause:
        clauses.append(f"direction IN {in_clause}")
        params.extend(direction_values)

    not_in_clause, excluded_sources = _build_in_clause(exclude_sources or [])
    if not_in_clause:
        clauses.append(f"source NOT IN {not_in_clause}")
        params.extend(excluded_sources)

    sql = f"""
        SELECT chat_name, observed_at, text, direction, source, message_time_text, context_json
        FROM messages
        WHERE {' AND '.join(clauses)}
        ORDER BY observed_at DESC, id DESC
        LIMIT ?
    """
    params.append(max(limit, 1))

    try:
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()

    messages = [row_to_archived_message(row) for row in rows]
    return list(reversed(messages))


def fetch_top_chat_names(
    *,
    directions: list[str] | None = None,
    exclude_sources: list[str] | None = None,
    limit: int = 20,
    db_path: Path = DEFAULT_DB_PATH,
) -> list[str]:
    conn = connect(db_path)
    clauses = ["1=1"]
    params: list[object] = []

    in_clause, direction_values = _build_in_clause(directions or [])
    if in_clause:
        clauses.append(f"direction IN {in_clause}")
        params.extend(direction_values)

    not_in_clause, excluded_sources = _build_in_clause(exclude_sources or [])
    if not_in_clause:
        clauses.append(f"source NOT IN {not_in_clause}")
        params.extend(excluded_sources)

    sql = f"""
        SELECT chat_name, COUNT(*) AS message_count
        FROM messages
        WHERE {' AND '.join(clauses)}
        GROUP BY chat_name
        ORDER BY message_count DESC, chat_name ASC
        LIMIT ?
    """
    params.append(max(limit, 1))

    try:
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()

    return [str(row[0]) for row in rows if str(row[0]).strip()]


def append_messages(
    records: list[ArchivedMessage],
    *,
    db_path: Path = DEFAULT_DB_PATH,
    export_dir: Path = DEFAULT_EXPORT_DIR,
) -> int:
    if not records:
        return 0

    export_dir.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    try:
        with conn:
            conn.executemany(
                """
                INSERT INTO messages (
                    chat_name,
                    observed_at,
                    text,
                    direction,
                    source,
                    message_time_text,
                    context_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        record.chat_name,
                        record.observed_at,
                        record.text,
                        record.direction,
                        record.source,
                        record.message_time_text,
                        json.dumps(record.context, ensure_ascii=False),
                    )
                    for record in records
                ],
            )
    finally:
        conn.close()

    grouped: dict[str, list[ArchivedMessage]] = {}
    for record in records:
        grouped.setdefault(record.chat_name, []).append(record)

    for chat_name, items in grouped.items():
        export_path = export_dir / f"{safe_chat_filename(chat_name)}.jsonl"
        with export_path.open("a", encoding="utf-8") as handle:
            for item in items:
                handle.write(json.dumps(asdict(item), ensure_ascii=False) + "\n")

    return len(records)
