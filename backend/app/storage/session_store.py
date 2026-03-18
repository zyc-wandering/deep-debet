from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from app.models import DebateSession, SessionState


class SessionStore:
    def __init__(self, persist_to_db: bool = True) -> None:
        self._sessions: Dict[str, DebateSession] = {}
        self._persist_to_db = persist_to_db

    def create(self, session: DebateSession) -> DebateSession:
        self._sessions[session.session_id] = session
        self.persist(session.session_id)
        return session

    def get(self, session_id: str) -> Optional[DebateSession]:
        return self._sessions.get(session_id)

    def update(self, session: DebateSession) -> None:
        self._sessions[session.session_id] = session
        self.persist(session.session_id)

    def mark_stop(self, session_id: str) -> bool:
        session = self._sessions.get(session_id)
        if not session:
            return False
        session.stop_requested = True
        if session.state == SessionState.running:
            session.state = SessionState.stopped
        self.persist(session_id)
        return True

    def persist(self, session_id: str) -> None:
        session = self._sessions.get(session_id)
        if not session:
            return
        if not session.debate_dir:
            return
        if self._persist_to_db:
            self._save_to_db(session)
        self._save_to_file(session)

    def _save_to_db(self, session: DebateSession) -> None:
        from app.storage.database import db
        try:
            db.save_session_meta(session)
            for msg in session.messages or []:
                db.append_message(msg)
            if session.structured_report:
                db.save_structured_report(session.session_id, session.structured_report)
            if session.report_path:
                report_content = ""
                report_file = Path(session.report_path)
                if report_file.exists():
                    report_content = report_file.read_text(encoding="utf-8")
                if report_content:
                    db.save_report_markdown(session.session_id, report_content)
            for fu in session.follow_up_messages or []:
                db.save_follow_up(fu)
        except Exception:
            pass

    def _save_to_file(self, session: DebateSession) -> None:
        debate_dir = Path(session.debate_dir)
        debate_dir.mkdir(parents=True, exist_ok=True)
        path = debate_dir / "session.json"
        path.write_text(session.model_dump_json(indent=2), encoding="utf-8")

    def load_all(self) -> None:
        from app.config import settings
        from app.storage.database import db
        settings.debates_dir.mkdir(parents=True, exist_ok=True)
        for debate_dir in settings.debates_dir.iterdir():
            if not debate_dir.is_dir():
                continue
            session_path = debate_dir / "session.json"
            if not session_path.exists():
                continue
            try:
                session_data = json.loads(session_path.read_text(encoding="utf-8"))
                session = DebateSession(**session_data)
                self._sessions[session.session_id] = session
                if self._persist_to_db:
                    try:
                        db.save_session_meta(session)
                        for msg in session.messages or []:
                            db.append_message(msg)
                        if session.structured_report:
                            db.save_structured_report(session.session_id, session.structured_report)
                        if session.report_path:
                            report_file = Path(session.report_path)
                            if report_file.exists():
                                db.save_report_markdown(
                                    session.session_id,
                                    report_file.read_text(encoding="utf-8"),
                                )
                        for fu in session.follow_up_messages or []:
                            db.save_follow_up(fu)
                    except Exception:
                        pass
            except Exception:
                continue

    def list_sessions(self, limit: int = 20, offset: int = 0, state: Optional[str] = None) -> tuple[List[Dict], int]:
        from app.storage.database import db
        return db.list_sessions(limit=limit, offset=offset, state_filter=state)

    def get_session_full(self, session_id: str) -> Optional[Dict]:
        from app.storage.database import db
        meta = db.get_session_meta(session_id)
        if not meta:
            return None
        meta["messages"] = db.get_messages(session_id)
        meta["structured_report"] = db.get_structured_report(session_id)
        meta["follow_up_messages"] = db.get_follow_ups(session_id)
        return meta

    def delete_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
        from app.storage.database import db
        db.delete_session(session_id)
