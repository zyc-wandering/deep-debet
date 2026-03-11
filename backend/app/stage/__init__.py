"""Debate stage executors for structured debate flow."""

from app.stage.base import DebateStageExecutor, StageContext, StageResult
from app.stage.opening_stage import OpeningStageExecutor
from app.stage.free_debate_stage import FreeDebateStageExecutor
from app.stage.closing_stage import ClosingStageExecutor
from app.stage.summary_stage import SummaryStageExecutor
from app.stage.stage_registry import StageRegistry

__all__ = [
    "DebateStageExecutor",
    "StageContext",
    "StageResult",
    "OpeningStageExecutor",
    "FreeDebateStageExecutor",
    "ClosingStageExecutor",
    "SummaryStageExecutor",
    "StageRegistry",
]
