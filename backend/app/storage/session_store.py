from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional

from app.models import DebateSession, SessionState


class SessionStore:
    def __init__(self) -> None:
        self._sessions: Dict[str, DebateSession] = {}

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
        debate_dir = Path(session.debate_dir)
        debate_dir.mkdir(parents=True, exist_ok=True)
        path = debate_dir / "session.json"
        path.write_text(session.model_dump_json(indent=2), encoding="utf-8")
