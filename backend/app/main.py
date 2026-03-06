from __future__ import annotations

from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, StreamingResponse

from app.config import ensure_directories, settings
from app.models import DebateStartRequest, DebateStopRequest, DebateStopResponse
from app.orchestrator import DebateOrchestrator
from app.providers.llm_openai_compat import OpenAICompatProvider
from app.providers.search_tavily import TavilySearchProvider
from app.storage.report_writer import ReportWriter
from app.storage.session_store import SessionStore
from app.utils.formatting import sse_event

ensure_directories()

app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

llm_provider = OpenAICompatProvider()
search_provider = TavilySearchProvider()
session_store = SessionStore()
report_writer = ReportWriter()


def _looks_high_risk(topic: str) -> bool:
    high_risk_markers = ["制造炸弹", "入侵系统", "洗钱", "恐怖袭击"]
    t = topic.lower()
    return any(m in t for m in high_risk_markers)


@app.get("/api/health")
async def health() -> dict:
    return {
        "status": "ok",
        "llm_enabled": llm_provider.enabled,
        "search_enabled": search_provider.enabled,
    }


@app.post("/api/debate/start")
async def start_debate(request: DebateStartRequest) -> StreamingResponse:
    if not settings.allow_unsafe_topics and _looks_high_risk(request.topic):
        raise HTTPException(status_code=400, detail="Topic rejected by minimal safety policy")

    orchestrator = DebateOrchestrator(
        llm=llm_provider,
        search=search_provider,
        session_store=session_store,
        report_writer=report_writer,
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

