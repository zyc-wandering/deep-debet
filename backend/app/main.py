from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, StreamingResponse, FileResponse

from app.config import ensure_directories, settings
from app.execution.turn_executor import DebaterTurnExecutor
from app.models import (
    DebateConfigureRequest,
    DebateConfirmRequest,
    DebateModelVariant,
    DebateStartRequest,
    DebateStopRequest,
    DebateStopResponse,
    FollowUpRequest,
)
from app.orchestrator import DebateOrchestrator
from app.providers.base import LLMProvider, SearchProvider
from app.providers.image_generation import ImageGenerationService
from app.providers.llm_openai_compat import OpenAICompatProvider
from app.providers.search_tavily import TavilySearchProvider
from app.stage import (
    ClosingStageExecutor,
    FreeDebateStageExecutor,
    OpeningStageExecutor,
    StageRegistry,
)
from app.storage.report_writer import ReportWriter
from app.storage.database import db
from app.storage.session_store import SessionStore
from app.storage.trace_store import TraceStore
from app.utils.formatting import sse_event
from app.utils.logger import debate_logger

ensure_directories()


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init()
    _get_or_create_session_store().load_all()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.frontend_origin,
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global singleton dependencies (lazy initialized)
_search_provider: SearchProvider | None = None
_session_store: SessionStore | None = None
_report_writer: ReportWriter | None = None
_trace_store: TraceStore | None = None
_image_service: ImageGenerationService | None = None
_turn_executor: DebaterTurnExecutor | None = None
_llm_provider: OpenAICompatProvider | None = None


def _get_or_create_search_provider() -> SearchProvider:
    global _search_provider
    if _search_provider is None:
        if settings.search_provider == "perplexity":
            from app.providers.search_perplexity import PerplexitySearchProvider

            _search_provider = PerplexitySearchProvider()
        else:
            _search_provider = TavilySearchProvider()
    return _search_provider


def _get_or_create_session_store() -> SessionStore:
    global _session_store
    if _session_store is None:
        _session_store = SessionStore()
    return _session_store


def _get_or_create_report_writer() -> ReportWriter:
    global _report_writer
    if _report_writer is None:
        _report_writer = ReportWriter()
    return _report_writer


def _get_or_create_trace_store() -> TraceStore:
    global _trace_store
    if _trace_store is None:
        _trace_store = TraceStore()
    return _trace_store


def _get_or_create_image_service() -> ImageGenerationService:
    global _image_service
    if _image_service is None:
        _image_service = ImageGenerationService()
    return _image_service


def _get_or_create_turn_executor() -> DebaterTurnExecutor:
    global _turn_executor
    if _turn_executor is None:
        _turn_executor = DebaterTurnExecutor()
    return _turn_executor


def _make_llm_provider(
    model_variant: DebateModelVariant = DebateModelVariant.lite,
) -> OpenAICompatProvider:
    """Factory function to create LLM provider based on model variant."""
    if model_variant == DebateModelVariant.pro:
        return OpenAICompatProvider(
            base_url=settings.openai_base_url_pro,
            api_key=settings.openai_api_key_pro,
            model=settings.openai_model_pro,
        )

    return OpenAICompatProvider(model=settings.openai_model)


def _get_or_create_llm_provider() -> OpenAICompatProvider:
    global _llm_provider
    if _llm_provider is None:
        _llm_provider = _make_llm_provider(
            DebateModelVariant.pro
            if settings.openai_api_key_pro
            else DebateModelVariant.lite
        )
    return _llm_provider


# Dependency providers for FastAPI injection
def get_search_provider() -> SearchProvider:
    """Dependency: Get search provider singleton."""
    return _get_or_create_search_provider()


def get_session_store() -> SessionStore:
    """Dependency: Get session store singleton."""
    return _get_or_create_session_store()


def get_report_writer() -> ReportWriter:
    """Dependency: Get report writer singleton."""
    return _get_or_create_report_writer()


def get_trace_store() -> TraceStore:
    """Dependency: Get trace store singleton."""
    return _get_or_create_trace_store()


def get_image_service() -> ImageGenerationService:
    """Dependency: Get image generation service singleton."""
    return _get_or_create_image_service()


def get_turn_executor() -> DebaterTurnExecutor:
    """Dependency: Get turn executor singleton."""
    return _get_or_create_turn_executor()


def get_stage_registry(
    turn_executor: DebaterTurnExecutor = Depends(get_turn_executor),
) -> StageRegistry:
    """Dependency: Get configured stage registry.

    This is where new debate stages can be registered.
    """
    registry = StageRegistry()
    registry.register(OpeningStageExecutor(turn_executor))
    registry.register(FreeDebateStageExecutor(turn_executor=turn_executor))
    registry.register(ClosingStageExecutor(turn_executor))
    return registry


def create_orchestrator(
    model_variant: DebateModelVariant,
    search: SearchProvider,
    store: SessionStore,
    writer: ReportWriter,
    images: ImageGenerationService,
    registry: StageRegistry,
    turn_exec: DebaterTurnExecutor,
) -> DebateOrchestrator:
    """Factory function: Create orchestrator with injected dependencies."""
    return DebateOrchestrator(
        llm=_make_llm_provider(model_variant),
        search=search,
        session_store=store,
        report_writer=writer,
        image_service=images,
        stage_registry=registry,
        turn_executor=turn_exec,
    )


def _serialize_traced_event(evt, store: SessionStore) -> str:
    payload = dict(evt.data)
    session_id = payload.get("session_id")
    if not session_id:
        return sse_event(evt.event, payload)

    session = store.get(session_id)
    trace_id = session.trace_id if session else session_id

    # Ensure trace store knows the debate directory
    trace_store = _get_or_create_trace_store()
    if session and session.debate_dir:
        trace_store.set_debate_dir(session_id, session.debate_dir)
    trace_ctx = (
        payload.get("_trace", {}) if isinstance(payload.get("_trace"), dict) else {}
    )
    envelope = trace_store.append_sse_event(
        session_id=session_id,
        trace_id=trace_id,
        event_name=evt.event,
        payload=payload,
        span_id=trace_ctx.get("span_id"),
        parent_span_id=trace_ctx.get("parent_span_id"),
        stage=payload.get("stage") or payload.get("phase") or trace_ctx.get("stage"),
    )

    trace_payload = {
        **trace_ctx,
        **envelope.as_dict(),
    }
    payload["_trace"] = trace_payload

    if session and session.trace_journal_path != envelope.journal_path:
        session.trace_journal_path = envelope.journal_path
        store.update(session)

    with debate_logger.session_context(session_id, trace_id):
        debate_logger.sse_event_sent(
            evt.event,
            session_id,
            len(str(payload)),
            envelope.event_seq,
            source_span_id=trace_ctx.get("span_id"),
            source_parent_span_id=trace_ctx.get("parent_span_id"),
        )

    return sse_event(evt.event, payload)


def _looks_high_risk(topic: str) -> bool:
    """Check if topic contains high-risk content markers."""
    high_risk_markers = [
        # Chinese
        "制造炸弹",
        "入侵系统",
        "洗钱",
        "恐怖袭击",
        # English
        "bomb making",
        "hacking",
        "money laundering",
        "terrorism",
        "terrorist attack",
        # Common variations
        "how to make a bomb",
        "how to hack",
        "how to launder money",
    ]
    t = topic.lower()
    return any(m in t for m in high_risk_markers)


@app.post("/api/debate/start")
async def start_debate(request: DebateStartRequest) -> StreamingResponse:
    """Start a new debate session.

    This endpoint initializes the debate workflow and returns an SSE stream
    of events including research results and focus options.
    """
    if not settings.allow_unsafe_topics and _looks_high_risk(request.topic):
        raise HTTPException(
            status_code=400, detail="Topic rejected by minimal safety policy"
        )

    # Create orchestrator with dependencies
    store = _get_or_create_session_store()
    orchestrator = create_orchestrator(
        model_variant=request.model_variant,
        search=_get_or_create_search_provider(),
        store=store,
        writer=_get_or_create_report_writer(),
        images=_get_or_create_image_service(),
        registry=get_stage_registry(_get_or_create_turn_executor()),
        turn_exec=_get_or_create_turn_executor(),
    )

    async def event_stream() -> AsyncGenerator[str, None]:
        async for evt in orchestrator.start(request):
            yield _serialize_traced_event(evt, store)
        # Explicit close marker for clients that need final newline flush.
        yield ": stream-end\n\n"

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(
        event_stream(), media_type="text/event-stream", headers=headers
    )


@app.post("/api/debate/configure")
async def configure_debate(request: DebateConfigureRequest) -> StreamingResponse:
    """Configure and run a debate after focus selection.

    This endpoint continues the debate workflow from the configuring phase,
    executes all debate stages, and generates the final report.
    """
    store = _get_or_create_session_store()
    session = store.get(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    valid_focus_ids = {option.id for option in session.focus_options}
    if request.pre_debate_config.selected_focus_id not in valid_focus_ids:
        raise HTTPException(status_code=400, detail="Selected focus option is invalid")

    # Create orchestrator with model variant from session
    orchestrator = create_orchestrator(
        model_variant=session.model_variant,
        search=_get_or_create_search_provider(),
        store=store,
        writer=_get_or_create_report_writer(),
        images=_get_or_create_image_service(),
        registry=get_stage_registry(_get_or_create_turn_executor()),
        turn_exec=_get_or_create_turn_executor(),
    )

    async def event_stream() -> AsyncGenerator[str, None]:
        async for evt in orchestrator.configure(request):
            yield _serialize_traced_event(evt, store)
        yield ": stream-end\n\n"

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(
        event_stream(), media_type="text/event-stream", headers=headers
    )


@app.post("/api/debate/confirm")
async def confirm_debate(request: DebateConfirmRequest) -> StreamingResponse:
    """Confirm debater lineup and start the debate.

    Called after the user reviews the debater drafting page and confirms.
    """
    store = _get_or_create_session_store()
    session = store.get(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Create orchestrator with model variant from session
    orchestrator = create_orchestrator(
        model_variant=session.model_variant,
        search=_get_or_create_search_provider(),
        store=store,
        writer=_get_or_create_report_writer(),
        images=_get_or_create_image_service(),
        registry=get_stage_registry(_get_or_create_turn_executor()),
        turn_exec=_get_or_create_turn_executor(),
    )

    async def event_stream() -> AsyncGenerator[str, None]:
        async for evt in orchestrator.confirm(request):
            yield _serialize_traced_event(evt, store)
        yield ": stream-end\n\n"

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(
        event_stream(), media_type="text/event-stream", headers=headers
    )


@app.post("/api/debate/stop")
async def stop_debate(
    request: DebateStopRequest,
    store: SessionStore = Depends(get_session_store),
) -> DebateStopResponse:
    """Request early termination of a running debate."""
    stopped = store.mark_stop(request.session_id)
    return DebateStopResponse(session_id=request.session_id, stopped=stopped)


@app.get("/api/debate/report", response_class=PlainTextResponse)
async def read_report(
    path: str = Query(..., min_length=1),
    writer: ReportWriter = Depends(get_report_writer),
) -> str:
    """Retrieve a generated debate report by path."""
    safe = writer.resolve_safe(path)
    if not safe or not safe.exists():
        raise HTTPException(status_code=404, detail="Report not found")
    return safe.read_text(encoding="utf-8")


@app.get("/api/images/{path:path}")
async def get_image(path: str) -> FileResponse:
    """Serve generated images from debate directories.

    Accepts either:
    - An absolute path to an image file (validated within debates_dir)
    - A relative path like {debate_folder}/images/{filename}
    """
    # Try as absolute path first
    image_path = Path(path)
    if not image_path.is_absolute():
        image_path = settings.debates_dir / path

    image_path = image_path.resolve()

    # Security check: must be within debates_dir
    try:
        image_path.relative_to(settings.debates_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Invalid path")

    if not image_path.exists() or not image_path.is_file():
        raise HTTPException(status_code=404, detail="Image not found")

    return FileResponse(
        str(image_path),
        media_type="image/png",
        filename=image_path.name,
    )


@app.post("/api/debate/followup")
async def follow_up(request: FollowUpRequest) -> StreamingResponse:
    """Post-debate follow-up Q&A with host or specific debater."""
    store = _get_or_create_session_store()
    session = store.get(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Create orchestrator with model variant from session
    orchestrator = create_orchestrator(
        model_variant=session.model_variant,
        search=_get_or_create_search_provider(),
        store=store,
        writer=_get_or_create_report_writer(),
        images=_get_or_create_image_service(),
        registry=get_stage_registry(_get_or_create_turn_executor()),
        turn_exec=_get_or_create_turn_executor(),
    )

    async def event_stream() -> AsyncGenerator[str, None]:
        async for evt in orchestrator.follow_up(
            session_id=request.session_id,
            target_role=request.target_role,
            question=request.question,
        ):
            yield _serialize_traced_event(evt, store)
        yield ": stream-end\n\n"

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(
        event_stream(), media_type="text/event-stream", headers=headers
    )


@app.get("/api/sessions")
async def list_sessions(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    state: str | None = Query(None),
    store: SessionStore = Depends(get_session_store),
) -> dict:
    """List all debate sessions with pagination."""
    sessions, total = store.list_sessions(limit=limit, offset=offset, state=state)
    return {"sessions": sessions, "total": total}


@app.get("/api/sessions/{session_id}")
async def get_session(
    session_id: str,
    store: SessionStore = Depends(get_session_store),
) -> dict:
    """Get full session data including messages, report and follow-ups."""
    data = store.get_session_full(session_id)
    if not data:
        raise HTTPException(status_code=404, detail="Session not found")
    return data


@app.delete("/api/sessions/{session_id}")
async def delete_session(
    session_id: str,
    store: SessionStore = Depends(get_session_store),
) -> dict:
    """Delete a session and its associated files."""
    data = store.get_session_full(session_id)
    if not data:
        raise HTTPException(status_code=404, detail="Session not found")
    debate_dir = data.get("debate_dir")
    if debate_dir:
        import shutil

        path = Path(debate_dir)
        if path.exists() and path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
    store.delete_session(session_id)
    return {"deleted": session_id}


@app.get("/api/health")
async def health() -> dict:
    """Health check endpoint."""
    search = _get_or_create_search_provider()
    images = _get_or_create_image_service()
    return {
        "status": "ok",
        "llm_enabled": _get_or_create_llm_provider().enabled,
        "search_enabled": getattr(search, "enabled", False),
        "image_generation_enabled": getattr(images.provider, "enabled", False),
        "architecture": "solid_stage_based",
    }
