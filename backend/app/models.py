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


class DebateStage(str, Enum):
    """Explicit debate stages for structured debate flow."""
    opening = "opening"
    free_debate = "free_debate"
    closing = "closing"
    summary = "summary"


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
    avatar_url: Optional[str] = None


class FocusDimension(BaseModel):
    """A focus dimension extracted by host for pre-debate configuration."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    description: str
    selected: bool = True


class PreDebateConfig(BaseModel):
    """User configuration for debate after host research."""
    dimensions: List[FocusDimension] = Field(default_factory=list)
    intensity: str = "balanced"  # "mild", "balanced", "intense"
    user_context: str = ""  # Optional user-provided context


class FollowUpMessage(BaseModel):
    """A follow-up message in the post-debate Q&A."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    target_role: str  # "host" or debater name
    question: str
    response: str = ""
    created_at: datetime = Field(default_factory=utc_now)


class ArgumentNode(BaseModel):
    """A node in the argument structure graph."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    speaker: str
    content: str
    turn_index: int
    targets: List[str] = Field(default_factory=list)  # IDs of nodes this responds to
    status: str = "claim"  # "claim", "support", "attack", "concession"
    focal_point: Optional[str] = None  # What issue this addresses


class DebateMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    speaker: str
    role: str
    content: str
    turn_index: int
    created_at: datetime = Field(default_factory=utc_now)
    citations: List[SearchResult] = Field(default_factory=list)
    stage: Optional[DebateStage] = None  # Which debate stage this message belongs to


class DebateStartRequest(BaseModel):
    topic: str = Field(min_length=5, max_length=240)
    debater_count: int = Field(default=3, ge=2, le=5)
    time_limit_sec: int = Field(default=360, ge=60, le=1800)
    max_turns: int = Field(default=24, ge=4, le=80)
    enable_debater_search: bool = False
    fun_mode: str = "persona_clash"

    # Pre-debate configuration (optional - can be set after research)
    pre_debate_config: Optional[PreDebateConfig] = None

    @model_validator(mode="after")
    def validate_fun_mode(self) -> "DebateStartRequest":
        allowed = {"persona_clash"}
        if self.fun_mode not in allowed:
            raise ValueError(f"fun_mode must be one of: {sorted(allowed)}")
        return self


class DebateConfigureRequest(BaseModel):
    """Request to configure debate after host research."""
    session_id: str
    pre_debate_config: PreDebateConfig


class FollowUpRequest(BaseModel):
    """Request for post-debate follow-up Q&A."""
    session_id: str
    target_role: str  # "host" or debater name
    question: str = Field(min_length=1, max_length=500)


class FollowUpResponse(BaseModel):
    """Response for follow-up request."""
    session_id: str
    follow_up_id: str
    target_role: str
    streaming: bool = True


class StructuredReport(BaseModel):
    """Structured report data for visualization."""
    background_summary: str = ""
    core_arguments: List[Dict[str, Any]] = Field(default_factory=list)
    clash_points: List[Dict[str, Any]] = Field(default_factory=list)
    synthesis: str = ""
    host_conclusion: str = ""
    argument_nodes: List[ArgumentNode] = Field(default_factory=list)


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

    # Stage tracking
    current_stage: Optional[DebateStage] = None
    stage_transcript: Dict[DebateStage, List[DebateMessage]] = Field(default_factory=dict)

    # Pre-debate configuration
    pre_debate_config: Optional[PreDebateConfig] = None

    # Follow-up thread
    follow_up_messages: List[FollowUpMessage] = Field(default_factory=list)

    # Structured report data
    structured_report: Optional[StructuredReport] = None
    report_path: Optional[str] = None


class SSEEvent(BaseModel):
    event: str
    data: Dict[str, Any]


class DebateStopRequest(BaseModel):
    session_id: str


class DebateStopResponse(BaseModel):
    session_id: str
    stopped: bool

