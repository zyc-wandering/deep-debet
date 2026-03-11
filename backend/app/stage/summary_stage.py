from __future__ import annotations

from typing import AsyncGenerator

from app.agents.host_agent import HostAgent
from app.models import DebateStage, SSEEvent
from app.providers.base import LLMProvider, SearchProvider
from app.stage.base import DebateStageExecutor, StageContext
from app.storage.report_writer import ReportWriter
from app.utils.formatting import chunk_text


class SummaryStageExecutor(DebateStageExecutor):
    """报告生成阶段：主持人总结辩论并生成报告"""

    def __init__(
        self,
        llm: LLMProvider,
        search: SearchProvider,
        report_writer: ReportWriter,
    ) -> None:
        self._llm = llm
        self._search = search
        self._report_writer = report_writer

    @property
    def stage_type(self) -> str:
        return "summarizing"

    @property
    def stage_name(self) -> str:
        return "Summarizing"

    @property
    def stage_description(self) -> str:
        return "The host is synthesizing disagreements, evidence, and final judgment."

    async def execute(self, ctx: StageContext) -> AsyncGenerator[SSEEvent, None]:
        """执行报告生成阶段"""
        host = HostAgent(self._llm, self._search)
        session = ctx.session

        structured_report = await host.summarize_debate_structured(
            ctx.topic,
            ctx.brief,
            session.messages,
            session.research_references,
        )
        session.structured_report = structured_report

        for chunk in chunk_text(structured_report.synthesis, chunk_size=44):
            yield SSEEvent(
                event="host_summary",
                data={"session_id": session.session_id, "chunk": chunk},
            )

        report = await host.summarize_debate(
            ctx.topic,
            ctx.brief,
            session.messages,
            session.research_references,
        )
        report_path = self._report_writer.write_markdown(ctx.topic, report)
        session.report_path = str(report_path.resolve())

        yield SSEEvent(
            event="structured_report",
            data={"session_id": session.session_id, "report": structured_report.model_dump()},
        )

    def should_advance(self, ctx: StageContext) -> bool:
        """总结阶段完成后直接结束"""
        return True
