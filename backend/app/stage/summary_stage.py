from __future__ import annotations

from time import monotonic
from typing import AsyncGenerator

from app.agents.host_agent import HostAgent
from app.models import SSEEvent
from app.providers.base import LLMProvider, SearchProvider
from app.stage.base import DebateStageExecutor, StageContext
from app.storage.report_writer import ReportWriter
from app.utils.formatting import chunk_text, with_trace_metadata
from app.utils.logger import debate_logger


class SummaryStageExecutor(DebateStageExecutor):
    """Generate the host summary, structured report, and markdown report file."""

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
        stage_start = monotonic()
        host = HostAgent(self._llm, self._search, debate_language=ctx.session.debate_language)
        session = ctx.session

        debate_logger.info(
            "Summary stage: Starting structured summary",
            event_type="summary_structured_start",
            session_id=session.session_id,
            message_count=len(session.messages),
            reference_count=len(session.research_references),
        )

        structured_start = monotonic()
        try:
            with debate_logger.span_context("summary:structured"):
                structured_report = await host.summarize_debate_structured(
                    ctx.topic,
                    ctx.brief,
                    session.messages,
                    session.research_references,
                )
            session.structured_report = structured_report
            debate_logger.info(
                "Summary stage: Structured summary completed",
                event_type="summary_structured_complete",
                session_id=session.session_id,
                duration_sec=monotonic() - structured_start,
                synthesis_length=len(structured_report.synthesis),
                argument_nodes_count=len(structured_report.argument_nodes),
            )
        except Exception:
            debate_logger.exception(
                "Summary stage: Structured summary failed",
                event_type="summary_structured_error",
                session_id=session.session_id,
                duration_sec=monotonic() - structured_start,
            )
            raise

        for chunk in chunk_text(structured_report.synthesis, chunk_size=44):
            yield SSEEvent(
                event="host_summary",
                data=with_trace_metadata({"session_id": session.session_id, "chunk": chunk}),
            )

        debate_logger.info(
            "Summary stage: Starting markdown report",
            event_type="summary_markdown_start",
            session_id=session.session_id,
        )
        markdown_start = monotonic()
        try:
            with debate_logger.span_context("summary:markdown"):
                report = await host.summarize_debate(
                    ctx.topic,
                    ctx.brief,
                    session.messages,
                    session.research_references,
                )
            debate_logger.info(
                "Summary stage: Markdown report completed",
                event_type="summary_markdown_complete",
                session_id=session.session_id,
                duration_sec=monotonic() - markdown_start,
                report_length=len(report),
            )
        except Exception:
            debate_logger.exception(
                "Summary stage: Markdown report failed",
                event_type="summary_markdown_error",
                session_id=session.session_id,
                duration_sec=monotonic() - markdown_start,
            )
            raise

        debate_logger.info(
            "Summary stage: Writing report to file",
            event_type="summary_write_start",
            session_id=session.session_id,
        )
        write_start = monotonic()
        try:
            with debate_logger.span_context("summary:write_report"):
                report_path = self._report_writer.write_markdown(ctx.topic, report)
            session.report_path = str(report_path.resolve())
            debate_logger.info(
                "Summary stage: Report written to file",
                event_type="summary_write_complete",
                session_id=session.session_id,
                duration_sec=monotonic() - write_start,
                path=str(report_path),
            )
        except Exception:
            debate_logger.exception(
                "Summary stage: Writing report failed",
                event_type="summary_write_error",
                session_id=session.session_id,
                duration_sec=monotonic() - write_start,
            )
            raise

        debate_logger.info(
            "Summary stage: Completed successfully",
            event_type="summary_stage_complete",
            session_id=session.session_id,
            total_duration_sec=monotonic() - stage_start,
        )

        yield SSEEvent(
            event="structured_report",
            data=with_trace_metadata({"session_id": session.session_id, "report": structured_report.model_dump()}),
        )

    def should_advance(self, ctx: StageContext) -> bool:
        return True
