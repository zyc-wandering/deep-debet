from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SessionState(str, Enum):
    running = "running"
    stopped = "stopped"
    done = "done"
    error = "error"


class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str
    published_date: Optional[str] = None


class DebaterConfig(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    background: str
    stance: str
    personality: str
    speaking_style: str = "direct"
    avatar_emoji: str = "🎙️"


class DebateMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    speaker: str
    role: str
    content: str
    turn_index: int
    created_at: datetime = Field(default_factory=utc_now)
    citations: List[SearchResult] = Field(default_factory=list)


class DebateStartRequest(BaseModel):
    topic: str = Field(min_length=5, max_length=240)
    debater_count: int = Field(default=3, ge=2, le=5)
    time_limit_sec: int = Field(default=360, ge=60, le=1800)
    max_turns: int = Field(default=24, ge=4, le=80)
    enable_debater_search: bool = False
    fun_mode: str = "persona_clash"

    @model_validator(mode="after")
    def validate_fun_mode(self) -> "DebateStartRequest":
        allowed = {"persona_clash"}
        if self.fun_mode not in allowed:
            raise ValueError(f"fun_mode must be one of: {sorted(allowed)}")
        return self


class DebateSession(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    topic: str
    state: SessionState = SessionState.running
    started_at: datetime = Field(default_factory=utc_now)
    deadline_at: datetime
    max_turns: int
    debaters: List[DebaterConfig] = Field(default_factory=list)
    brief: str = ""
    messages: List[DebateMessage] = Field(default_factory=list)
    stop_requested: bool = False
    error: Optional[str] = None


class SSEEvent(BaseModel):
    event: str
    data: Dict[str, Any]


class DebateStopRequest(BaseModel):
    session_id: str


class DebateStopResponse(BaseModel):
    session_id: str
    stopped: bool

