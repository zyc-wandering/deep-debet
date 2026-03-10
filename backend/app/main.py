from __future__ import annotations

from typing import AsyncGenerator
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import ensure_directories, settings
from app.models import DebateStartRequest, DebateStopRequest, DebateStopResponse, FollowUpRequest
from app.orchestrator import DebateOrchestrator
from app.providers.image_generation import ImageGenerationService
from app.providers.llm_openai_compat import OpenAICompatProvider
from app.providers.search_tavily import TavilySearchProvider
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

llm_provider = OpenAICompatProvider()
search_provider = TavilySearchProvider()
session_store = SessionStore()
report_writer = ReportWriter()
image_service = ImageGenerationService()


def _looks_high_risk(topic: str) -> bool:
    high_risk_markers = ["制造炸弹", "入侵系统", "洗钱", "恐怖袭击"]
    t = topic.lower()
    return any(m in t for m in high_risk_markers)


@app.post("/api/debate/start")
async def start_debate(request: DebateStartRequest) -> StreamingResponse:
    if not settings.allow_unsafe_topics and _looks_high_risk(request.topic):
        raise HTTPException(status_code=400, detail="Topic rejected by minimal safety policy")

    orchestrator = DebateOrchestrator(
        llm=llm_provider,
        search=search_provider,
        session_store=session_store,
        report_writer=report_writer,
        image_service=image_service,
    )

    async def event_stream() -> AsyncGenerator[str, None]:
        async for evt in orchestrator.run(request):
            yield sse_event(evt.event, evt.data)
        # Explicit close marker for clients that need final newline flush.
        yield ": stream-end\n\n"

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=headers)


@app.post("/api/debate/stop")
async def stop_debate(request: DebateStopRequest) -> DebateStopResponse:
    stopped = session_store.mark_stop(request.session_id)
    return DebateStopResponse(session_id=request.session_id, stopped=stopped)


@app.get("/api/debate/report", response_class=PlainTextResponse)
async def read_report(path: str = Query(..., min_length=1)) -> str:
    safe = report_writer.resolve_safe(path)
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
    orchestrator = DebateOrchestrator(
        llm=llm_provider,
        search=search_provider,
        session_store=session_store,
        report_writer=report_writer,
        image_service=image_service,
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
    return {
        "status": "ok",
        "llm_enabled": llm_provider.enabled,
        "search_enabled": search_provider.enabled,
        "image_generation_enabled": image_service.provider.enabled,
    }
