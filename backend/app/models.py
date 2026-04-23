from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


SUPPORTED_DEBATER_COUNTS = (2, 4, 6, 8)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SessionState(str, Enum):
    running = "running"
    configuring = "configuring"
    drafting = "drafting"
    stopped = "stopped"
    done = "done"
    error = "error"


class DebateStage(str, Enum):
    """Explicit debate stages for structured debate flow."""
    opening = "opening"
    free_debate = "free_debate"
    closing = "closing"
    summary = "summary"


class DebateModelVariant(str, Enum):
    lite = "lite"
    pro = "pro"


class DebateLanguage(str, Enum):
    zh = "zh"
    en = "en"


class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str
    published_date: Optional[str] = None


class DebaterConfig(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    age: str = ""
    ethnicity: str = ""
    background: str
    stance: str
    personality: str
    speaking_style: str = "direct"
    avatar_emoji: str = "🎙️"
    avatar_url: Optional[str] = None
    gender: Optional[str] = None
    avatar_id: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def coerce_age_to_str(cls, values: Any) -> Any:
        """LLM may return age as int; coerce to string."""
        if isinstance(values, dict) and "age" in values:
            values["age"] = str(values["age"])
        return values


class FocusOption(BaseModel):
    """A topic-grounded focus option proposed by the host."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    description: str


class PreDebateConfig(BaseModel):
    """User configuration collected after host research."""
    selected_focus_id: str = Field(min_length=1)
    intensity: Literal["mild", "balanced", "intense"] = "balanced"
    user_context: str = ""


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
    debater_count: int = Field(default=4, ge=2, le=8)
    time_limit_sec: int = Field(default=1800, ge=60, le=1800)
    max_turns: int = Field(default=24, ge=4, le=80)
    enable_debater_search: bool = True
    debate_language: DebateLanguage = DebateLanguage.zh
    model_variant: DebateModelVariant = DebateModelVariant.lite
    fun_mode: str = "persona_clash"

    @model_validator(mode="after")
    def validate_request(self) -> "DebateStartRequest":
        if self.debater_count not in SUPPORTED_DEBATER_COUNTS:
            raise ValueError(
                f"debater_count must be one of: {', '.join(str(count) for count in SUPPORTED_DEBATER_COUNTS)}"
            )
        allowed = {"persona_clash"}
        if self.fun_mode not in allowed:
            raise ValueError(f"fun_mode must be one of: {sorted(allowed)}")
        return self


class DebateConfigureRequest(BaseModel):
    """Request to configure debate after host research."""
    session_id: str
    pre_debate_config: PreDebateConfig


class DebateConfirmRequest(BaseModel):
    """Request to confirm debater lineup and start the debate."""
    session_id: str
    debater_ids: List[str] = Field(default_factory=list)  # ordered main debater IDs; empty = use current lineup


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


class HostConclusion(BaseModel):
    """Structured host conclusion with multiple reasoning dimensions."""
    winning_argument: str = ""
    strongest_debater: str = ""
    reasoning: str = ""
    reasoning_list: List[str] = Field(default_factory=list)


class StructuredReport(BaseModel):
    """Structured report data for visualization."""
    background_summary: str = ""
    core_arguments: List[Dict[str, Any]] = Field(default_factory=list)
    clash_points: List[Dict[str, Any]] = Field(default_factory=list)
    synthesis: str = ""
    host_conclusion: Union[str, HostConclusion] = ""
    argument_nodes: List[ArgumentNode] = Field(default_factory=list)


class DebateSession(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    trace_id: str = Field(default_factory=lambda: str(uuid4()))
    topic: str
    model_variant: DebateModelVariant = DebateModelVariant.lite
    debate_language: DebateLanguage = DebateLanguage.zh
    state: SessionState = SessionState.running
    started_at: datetime = Field(default_factory=utc_now)
    deadline_at: Optional[datetime] = None
    debater_count: int = 4
    time_limit_sec: int = 360
    max_turns: int
    enable_debater_search: bool = True
    fun_mode: str = "persona_clash"
    debaters: List[DebaterConfig] = Field(default_factory=list)
    substitute_debaters: List[DebaterConfig] = Field(default_factory=list)
    brief: str = ""
    research_references: List[SearchResult] = Field(default_factory=list)
    messages: List[DebateMessage] = Field(default_factory=list)
    stop_requested: bool = False
    error: Optional[str] = None

    # Stage tracking
    current_stage: Optional[DebateStage] = None
    stage_transcript: Dict[DebateStage, List[DebateMessage]] = Field(default_factory=dict)

    # Pre-debate configuration
    focus_options: List[FocusOption] = Field(default_factory=list)
    pre_debate_config: Optional[PreDebateConfig] = None

    # Follow-up thread
    follow_up_messages: List[FollowUpMessage] = Field(default_factory=list)

    # Per-debate directory (all artifacts stored here)
    debate_dir: Optional[str] = None

    # Structured report data
    structured_report: Optional[StructuredReport] = None
    report_path: Optional[str] = None
    trace_journal_path: Optional[str] = None


class SSEEvent(BaseModel):
    event: str
    data: Dict[str, Any]


class DebateStopRequest(BaseModel):
    session_id: str


class DebateStopResponse(BaseModel):
    session_id: str
    stopped: bool
