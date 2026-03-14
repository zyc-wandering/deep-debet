from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncGenerator, List

from app.models import DebateSession, DebateMessage, FocusOption, SSEEvent
from app.agents.debater_agent import DebaterAgent


@dataclass
class StageContext:
    """阶段执行上下文"""
    session: DebateSession
    debater_agents: List[DebaterAgent]
    topic: str
    brief: str
    intensity: str
    selected_focus: FocusOption | None
    user_context: str
    start_turn_id: int


@dataclass
class StageResult:
    """阶段执行结果"""
    messages: List[DebateMessage]
    final_turn_id: int


class DebateStageExecutor(ABC):
    """辩论阶段执行器抽象基类"""

    @property
    @abstractmethod
    def stage_type(self) -> str:
        """阶段标识，如 'opening', 'free_debate' 等"""
        pass

    @property
    @abstractmethod
    def stage_name(self) -> str:
        """阶段显示名称"""
        pass

    @property
    @abstractmethod
    def stage_description(self) -> str:
        """阶段描述"""
        pass

    @abstractmethod
    async def execute(
        self,
        ctx: StageContext,
    ) -> AsyncGenerator[SSEEvent, None]:
        """执行阶段，产出SSE事件流"""
        pass

    def should_advance(self, ctx: StageContext) -> bool:
        """判断是否应该进入下一阶段，子类可覆盖"""
        return True
