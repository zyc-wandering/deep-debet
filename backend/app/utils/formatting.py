from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Dict, Iterable


def slugify(text: str) -> str:
    s = text.strip().lower()
    s = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s or "debate-topic"


def utc_now_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def chunk_text(text: str, chunk_size: int = 28) -> Iterable[str]:
    if not text:
        return
    for i in range(0, len(text), chunk_size):
        yield text[i : i + chunk_size]


def sse_event(event: str, data: Dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def with_trace_metadata(data: Dict) -> Dict:
    from app.utils.logger import debate_logger

    payload = dict(data)
    trace = {key: value for key, value in debate_logger.current_trace_context().items() if value is not None}
    if trace:
        payload["_trace"] = trace
    return payload
