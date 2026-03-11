from __future__ import annotations

from typing import AsyncGenerator
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import ensure_directories, settings
from app.execution.turn_executor import DebaterTurnExecutor
from app.models import (
    DebateConfigureRequest,
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
from app.storage.session_store import SessionStore
from app.utils.formatting import sse_event

ensure_directories()

# Ensure images directory exists
images_dir = settings.data_dir / "images"
images_dir.mkdir(parents=True, exist_ok=True)

app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for images
app.mount("/api/images", StaticFiles(directory=str(images_dir)), name="images")

# Global singleton dependencies
search_provider = TavilySearchProvider()
session_store = SessionStore()
report_writer = ReportWriter()
image_service = ImageGenerationService()
turn_executor = DebaterTurnExecutor()


def _make_llm_provider(model_variant: DebateModelVariant = DebateModelVariant.lite) -> OpenAICompatProvider:
    """Factory function to create LLM provider based on model variant."""
    if model_variant == DebateModelVariant.pro:
        return OpenAICompatProvider(
            model=settings.openai_model_pro,
            api_style="responses",
            response_tools=[{"type": "web_search", "max_keyword": 3}],
        )

    return OpenAICompatProvider(model=settings.openai_model)


llm_provider = _make_llm_provider()


# Dependency providers for FastAPI injection
def get_search_provider() -> SearchProvider:
    """Dependency: Get search provider singleton."""
    return search_provider


def get_session_store() -> SessionStore:
    """Dependency: Get session store singleton."""
    return session_store


def get_report_writer() -> ReportWriter:
    """Dependency: Get report writer singleton."""
    return report_writer


def get_image_service() -> ImageGenerationService:
    """Dependency: Get image generation service singleton."""
    return image_service


def get_turn_executor() -> DebaterTurnExecutor:
    """Dependency: Get turn executor singleton."""
    return turn_executor


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


def _looks_high_risk(topic: str) -> bool:
    """Check if topic contains high-risk content markers."""
    high_risk_markers = ["制造炸弹", "入侵系统", "洗钱", "恐怖袭击"]
    t = topic.lower()
    return any(m in t for m in high_risk_markers)


@app.post("/api/debate/start")
async def start_debate(request: DebateStartRequest) -> StreamingResponse:
    """Start a new debate session.

    This endpoint initializes the debate workflow and returns an SSE stream
    of events including research results and focus options.
    """
    if not settings.allow_unsafe_topics and _looks_high_risk(request.topic):
        raise HTTPException(status_code=400, detail="Topic rejected by minimal safety policy")

    # Create orchestrator with dependencies
    orchestrator = create_orchestrator(
        model_variant=request.model_variant,
        search=search_provider,
        store=session_store,
        writer=report_writer,
        images=image_service,
        registry=get_stage_registry(turn_executor),
        turn_exec=turn_executor,
    )

    async def event_stream() -> AsyncGenerator[str, None]:
        async for evt in orchestrator.start(request):
            yield sse_event(evt.event, evt.data)
        # Explicit close marker for clients that need final newline flush.
        yield ": stream-end\n\n"

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=headers)


@app.post("/api/debate/configure")
async def configure_debate(request: DebateConfigureRequest) -> StreamingResponse:
    """Configure and run a debate after focus selection.

    This endpoint continues the debate workflow from the configuring phase,
    executes all debate stages, and generates the final report.
    """
    session = session_store.get(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    valid_focus_ids = {option.id for option in session.focus_options}
    if request.pre_debate_config.selected_focus_id not in valid_focus_ids:
        raise HTTPException(status_code=400, detail="Selected focus option is invalid")

    # Create orchestrator with model variant from session
    orchestrator = create_orchestrator(
        model_variant=session.model_variant,
        search=search_provider,
        store=session_store,
        writer=report_writer,
        images=image_service,
        registry=get_stage_registry(turn_executor),
        turn_exec=turn_executor,
    )

    async def event_stream() -> AsyncGenerator[str, None]:
        async for evt in orchestrator.configure(request):
            yield sse_event(evt.event, evt.data)
        yield ": stream-end\n\n"

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=headers)


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


@app.get("/api/images/{filename}")
async def get_image(filename: str) -> FileResponse:
    """Serve generated images."""
    image_path = images_dir / filename
    # Security check: ensure file is within images_dir
    try:
        image_path.relative_to(images_dir)
    except ValueError:
        raise HTTPException(status_code=403, detail="Invalid path")

    if not image_path.exists() or not image_path.is_file():
        raise HTTPException(status_code=404, detail="Image not found")

    return FileResponse(
        str(image_path),
        media_type="image/png",
        filename=filename,
    )


@app.post("/api/debate/followup")
async def follow_up(request: FollowUpRequest) -> StreamingResponse:
    """Post-debate follow-up Q&A with host or specific debater."""
    session = session_store.get(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Create orchestrator with model variant from session
    orchestrator = create_orchestrator(
        model_variant=session.model_variant,
        search=search_provider,
        store=session_store,
        writer=report_writer,
        images=image_service,
        registry=get_stage_registry(turn_executor),
        turn_exec=turn_executor,
    )

    async def event_stream() -> AsyncGenerator[str, None]:
        async for evt in orchestrator.follow_up(
            session_id=request.session_id,
            target_role=request.target_role,
            question=request.question,
        ):
            yield sse_event(evt.event, evt.data)
        yield ": stream-end\n\n"

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=headers)


@app.get("/api/health")
async def health() -> dict:
    """Health check endpoint."""
    return {
        "status": "ok",
        "llm_enabled": llm_provider.enabled,
        "search_enabled": search_provider.enabled,
        "image_generation_enabled": image_service.provider.enabled,
        "architecture": "solid_stage_based",
    }
