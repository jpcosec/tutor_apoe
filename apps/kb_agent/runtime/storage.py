from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_RUNTIME_ROOT = Path(__file__).resolve().parent.parent
_INSTANCES_ROOT = _RUNTIME_ROOT / 'instances'


def resolve_db_path(pack_id: str) -> Path:
    explicit = os.environ.get('KB_DB_PATH')
    if explicit:
        return Path(explicit).expanduser().resolve()

    instance_id = os.environ.get('KB_INSTANCE', 'default')
    if Path('/data').exists():
        return Path('/data') / 'kb_agent' / pack_id / instance_id / 'kb_agent.db'
    return (_INSTANCES_ROOT / pack_id / instance_id / 'kb_agent.db').resolve()


class Storage:
    def __init__(self, pack_id: str):
        self.db_path = resolve_db_path(pack_id)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def utc_now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS conversations (
                    conversation_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    title TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY(user_id) REFERENCES users(user_id)
                );

                CREATE TABLE IF NOT EXISTS turns (
                    turn_id TEXT NOT NULL,
                    conversation_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    turn_index INTEGER NOT NULL,
                    user_message TEXT NOT NULL,
                    assistant_message TEXT NOT NULL,
                    mesa_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (conversation_id, turn_id),
                    FOREIGN KEY(conversation_id) REFERENCES conversations(conversation_id),
                    FOREIGN KEY(user_id) REFERENCES users(user_id)
                );

                CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON conversations(user_id);
                CREATE INDEX IF NOT EXISTS idx_turns_conversation_id ON turns(conversation_id);
                """
            )

    def ensure_user(self, user_id: str, metadata: dict[str, Any] | None = None) -> None:
        now = self.utc_now()
        metadata_json = json.dumps(metadata or {}, ensure_ascii=False)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO users (user_id, created_at, last_seen_at, metadata_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                  last_seen_at = excluded.last_seen_at,
                  metadata_json = CASE
                    WHEN excluded.metadata_json != '{}' THEN excluded.metadata_json
                    ELSE users.metadata_json
                  END
                """,
                (user_id, now, now, metadata_json),
            )

    def ensure_conversation(self, conversation_id: str, user_id: str, title: str | None = None, metadata: dict[str, Any] | None = None) -> None:
        now = self.utc_now()
        metadata_json = json.dumps(metadata or {}, ensure_ascii=False)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO conversations (conversation_id, user_id, created_at, updated_at, title, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(conversation_id) DO UPDATE SET
                  updated_at = excluded.updated_at,
                  title = COALESCE(conversations.title, excluded.title),
                  metadata_json = CASE
                    WHEN excluded.metadata_json != '{}' THEN excluded.metadata_json
                    ELSE conversations.metadata_json
                  END
                """,
                (conversation_id, user_id, now, now, title, metadata_json),
            )

    def get_conversation_turns(self, conversation_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT turn_id, conversation_id, user_id, turn_index, user_message, assistant_message, mesa_json, created_at
                FROM turns
                WHERE conversation_id = ?
                ORDER BY turn_index ASC
                """,
                (conversation_id,),
            ).fetchall()
        turns = []
        for row in rows:
            turns.append({
                'turn_id': row['turn_id'],
                'conversation_id': row['conversation_id'],
                'user_id': row['user_id'],
                'turn_index': row['turn_index'],
                'user_message': row['user_message'],
                'assistant_message': row['assistant_message'],
                'mesa': json.loads(row['mesa_json']),
                'created_at': row['created_at'],
            })
        return turns

    def save_turn(self, conversation_id: str, user_id: str, turn_id: str, user_message: str, assistant_message: str, mesa: dict[str, Any]) -> dict[str, Any]:
        now = self.utc_now()
        turns = self.get_conversation_turns(conversation_id)
        turn_index = len(turns) + 1
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO turns (turn_id, conversation_id, user_id, turn_index, user_message, assistant_message, mesa_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (turn_id, conversation_id, user_id, turn_index, user_message, assistant_message, json.dumps(mesa, ensure_ascii=False), now),
            )
            conn.execute(
                'UPDATE conversations SET updated_at = ? WHERE conversation_id = ?',
                (now, conversation_id),
            )
        return {
            'turn_id': turn_id,
            'conversation_id': conversation_id,
            'user_id': user_id,
            'turn_index': turn_index,
            'user_message': user_message,
            'assistant_message': assistant_message,
            'mesa': mesa,
            'created_at': now,
        }

    def get_conversation(self, conversation_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            convo = conn.execute(
                'SELECT conversation_id, user_id, created_at, updated_at, title, metadata_json FROM conversations WHERE conversation_id = ?',
                (conversation_id,),
            ).fetchone()
        if not convo:
            return None
        return {
            'conversation_id': convo['conversation_id'],
            'user_id': convo['user_id'],
            'created_at': convo['created_at'],
            'updated_at': convo['updated_at'],
            'title': convo['title'],
            'metadata': json.loads(convo['metadata_json'] or '{}'),
            'turns': self.get_conversation_turns(conversation_id),
        }

    def get_user_conversations(self, user_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT conversation_id, user_id, created_at, updated_at, title, metadata_json
                FROM conversations
                WHERE user_id = ?
                ORDER BY updated_at DESC
                """,
                (user_id,),
            ).fetchall()
        return [
            {
                'conversation_id': row['conversation_id'],
                'user_id': row['user_id'],
                'created_at': row['created_at'],
                'updated_at': row['updated_at'],
                'title': row['title'],
                'metadata': json.loads(row['metadata_json'] or '{}'),
            }
            for row in rows
        ]
