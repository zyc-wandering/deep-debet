from __future__ import annotations

from typing import Dict, List, Optional

from app.stage.base import DebateStageExecutor


class StageRegistry:
    """阶段执行器注册表"""

    def __init__(self) -> None:
        self._executors: Dict[str, DebateStageExecutor] = {}

    def register(self, executor: DebateStageExecutor) -> None:
        """注册阶段执行器"""
        self._executors[executor.stage_type] = executor

    def get(self, stage_type: str) -> Optional[DebateStageExecutor]:
        """获取阶段执行器"""
        return self._executors.get(stage_type)

    def list_stages(self) -> List[str]:
        """列出所有已注册的阶段"""
        return list(self._executors.keys())

    def create_pipeline(self, stage_order: List[str]) -> List[DebateStageExecutor]:
        """根据阶段顺序创建执行器管道"""
        pipeline = []
        for stage_type in stage_order:
            executor = self._executors.get(stage_type)
            if executor:
                pipeline.append(executor)
        return pipeline
