from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Dict

from app.config import settings


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class TraceEnvelope:
    trace_id: str
    span_id: str | None
    parent_span_id: str | None
    event_seq: int
    emitted_at: str
    journal_path: str

    def as_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "event_seq": self.event_seq,
            "emitted_at": self.emitted_at,
            "journal_path": self.journal_path,
        }


class TraceStore:
    def __init__(self, trace_dir: Path | None = None) -> None:
        self.trace_dir = trace_dir or settings.trace_dir
        self._seq_by_session: dict[str, int] = {}
        self._locks: dict[str, Lock] = {}

    def path_for(self, session_id: str) -> Path:
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        return self.trace_dir / f"{session_id}.jsonl"

    def append_sse_event(
        self,
        session_id: str,
        trace_id: str,
        event_name: str,
        payload: Dict[str, Any],
        *,
        span_id: str | None,
        parent_span_id: str | None,
        stage: str | None,
    ) -> TraceEnvelope:
        lock = self._locks.setdefault(session_id, Lock())
        with lock:
            seq = self._next_seq(session_id)
            emitted_at = _utc_now_iso()
            path = self.path_for(session_id)
            entry = {
                "trace_id": trace_id,
                "session_id": session_id,
                "event_seq": seq,
                "event": event_name,
                "emitted_at": emitted_at,
                "span_id": span_id,
                "parent_span_id": parent_span_id,
                "stage": stage,
                "payload": payload,
            }
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False, default=str))
                fh.write("\n")

        return TraceEnvelope(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            event_seq=seq,
            emitted_at=emitted_at,
            journal_path=str(path.resolve()),
        )

    def _next_seq(self, session_id: str) -> int:
        current = self._seq_by_session.get(session_id)
        if current is None:
            current = self._load_existing_seq(session_id)
        current += 1
        self._seq_by_session[session_id] = current
        return current

    def _load_existing_seq(self, session_id: str) -> int:
        path = self.path_for(session_id)
        if not path.exists():
            return 0
        with path.open("r", encoding="utf-8") as fh:
            return sum(1 for _ in fh)
