from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional

from app.config import settings


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    trace_id TEXT NOT NULL,
    topic TEXT NOT NULL,
    state TEXT NOT NULL,
    debate_language TEXT NOT NULL,
    model_variant TEXT NOT NULL,
    debater_count INTEGER NOT NULL,
    time_limit_sec INTEGER NOT NULL,
    max_turns INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    deadline_at TEXT,
    debate_dir TEXT,
    report_path TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    speaker TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    turn_index INTEGER NOT NULL,
    stage TEXT NOT NULL,
    citations TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

CREATE TABLE IF NOT EXISTS structured_reports (
    session_id TEXT PRIMARY KEY,
    background_summary TEXT,
    synthesis TEXT,
    host_conclusion TEXT,
    core_arguments TEXT,
    clash_points TEXT,
    argument_nodes TEXT,
    report_markdown TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

CREATE TABLE IF NOT EXISTS follow_up_messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    target_role TEXT NOT NULL,
    question TEXT NOT NULL,
    response TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_followup_session ON follow_up_messages(session_id);
CREATE INDEX IF NOT EXISTS idx_sessions_state ON sessions(state);
CREATE INDEX IF NOT EXISTS idx_sessions_started ON sessions(started_at DESC);
"""


class Database:
    _instance: Optional["Database"] = None
    _lock = Lock()

    def __new__(cls) -> "Database":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        self._db_path = settings.data_dir / "debate.db"
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA foreign_keys = ON")
        return self._conn

    def init(self) -> None:
        conn = self._get_conn()
        conn.executescript(CREATE_TABLES_SQL)
        conn.commit()

    def save_session_meta(self, session: Any) -> None:
        conn = self._get_conn()
        now = _utc_now_iso()
        conn.execute(
            """
            INSERT INTO sessions (
                session_id, trace_id, topic, state, debate_language, model_variant,
                debater_count, time_limit_sec, max_turns, started_at, deadline_at,
                debate_dir, report_path, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                state=excluded.state,
                debate_dir=excluded.debate_dir,
                report_path=excluded.report_path,
                updated_at=excluded.updated_at
            """,
            (
                session.session_id,
                session.trace_id,
                session.topic,
                session.state.value if hasattr(session.state, "value") else str(session.state),
                session.debate_language.value if hasattr(session.debate_language, "value") else str(session.debate_language),
                session.model_variant.value if hasattr(session.model_variant, "value") else str(session.model_variant),
                session.debater_count,
                session.time_limit_sec,
                session.max_turns,
                session.started_at.isoformat() if isinstance(session.started_at, datetime) else session.started_at,
                session.deadline_at.isoformat() if session.deadline_at else None,
                session.debate_dir,
                session.report_path,
                now,
                now,
            ),
        )
        conn.commit()

    def append_message(self, msg: Any) -> None:
        conn = self._get_conn()
        citations_json = json.dumps(
            [c.model_dump() if hasattr(c, "model_dump") else c for c in (msg.citations or [])],
            ensure_ascii=False,
            default=str,
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO messages (id, session_id, speaker, role, content, turn_index, stage, citations, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                msg.id,
                msg.speaker,
                msg.role,
                msg.content,
                msg.turn_index,
                msg.stage.value if hasattr(msg.stage, "value") else str(msg.stage) if msg.stage else None,
                citations_json,
                msg.created_at.isoformat() if isinstance(msg.created_at, datetime) else msg.created_at,
            ),
        )
        conn.commit()

    def save_structured_report(self, session_id: str, report: Any) -> None:
        conn = self._get_conn()
        now = _utc_now_iso()
        conn.execute(
            """
            INSERT INTO structured_reports (
                session_id, background_summary, synthesis, host_conclusion,
                core_arguments, clash_points, argument_nodes, report_markdown
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                background_summary=excluded.background_summary,
                synthesis=excluded.synthesis,
                host_conclusion=excluded.host_conclusion,
                core_arguments=excluded.core_arguments,
                clash_points=excluded.clash_points,
                argument_nodes=excluded.argument_nodes,
                report_markdown=excluded.report_markdown
            """,
            (
                session_id,
                getattr(report, "background_summary", "") or "",
                getattr(report, "synthesis", "") or "",
                json.dumps(report.host_conclusion, ensure_ascii=False, default=str) if hasattr(report, "host_conclusion") else json.dumps(report.get("host_conclusion", ""), ensure_ascii=False, default=str),
                json.dumps(getattr(report, "core_arguments", []) or [], ensure_ascii=False, default=str),
                json.dumps(getattr(report, "clash_points", []) or [], ensure_ascii=False, default=str),
                json.dumps(getattr(report, "argument_nodes", []) or [], ensure_ascii=False, default=str),
                getattr(report, "_raw_markdown", "") or "",
            ),
        )
        conn.commit()

    def save_report_markdown(self, session_id: str, markdown: str) -> None:
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO structured_reports (session_id, report_markdown) VALUES (?, ?) "
            "ON CONFLICT(session_id) DO UPDATE SET report_markdown=excluded.report_markdown",
            (session_id, markdown),
        )
        conn.commit()

    def save_follow_up(self, msg: Any) -> None:
        conn = self._get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO follow_up_messages (id, session_id, target_role, question, response, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                msg.id,
                msg.session_id,
                msg.target_role,
                msg.question,
                getattr(msg, "response", "") or "",
                msg.created_at.isoformat() if isinstance(msg.created_at, datetime) else msg.created_at,
            ),
        )
        conn.commit()

    def get_session_meta(self, session_id: str) -> Optional[Dict[str, Any]]:
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        if not row:
            return None
        return dict(row)

    def get_messages(self, session_id: str) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY turn_index ASC, created_at ASC",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_structured_report(self, session_id: str) -> Optional[Dict[str, Any]]:
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM structured_reports WHERE session_id = ?", (session_id,)).fetchone()
        if not row:
            return None
        return dict(row)

    def get_follow_ups(self, session_id: str) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM follow_up_messages WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def list_sessions(
        self,
        limit: int = 20,
        offset: int = 0,
        state_filter: Optional[str] = None,
    ) -> tuple[List[Dict[str, Any]], int]:
        conn = self._get_conn()
        if state_filter:
            rows = conn.execute(
                "SELECT * FROM sessions WHERE state = ? ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                (state_filter, limit, offset),
            ).fetchall()
            total = conn.execute(
                "SELECT COUNT(*) FROM sessions WHERE state = ?", (state_filter,),
            ).fetchone()[0]
        else:
            rows = conn.execute(
                "SELECT * FROM sessions ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
            total = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        return [dict(r) for r in rows], total

    def delete_session(self, session_id: str) -> None:
        conn = self._get_conn()
        conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM structured_reports WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM follow_up_messages WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        conn.commit()


db = Database()
