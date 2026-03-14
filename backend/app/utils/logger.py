from __future__ import annotations

import asyncio
import json
import logging
import sys
import traceback
from contextvars import ContextVar
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

from app.config import settings

session_id_context: ContextVar[Optional[str]] = ContextVar("session_id", default=None)
trace_id_context: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)
stage_context: ContextVar[Optional[str]] = ContextVar("stage", default=None)
span_id_context: ContextVar[Optional[str]] = ContextVar("span_id", default=None)
parent_span_id_context: ContextVar[Optional[str]] = ContextVar("parent_span_id", default=None)
span_name_context: ContextVar[Optional[str]] = ContextVar("span_name", default=None)


def _new_span_id() -> str:
    return uuid4().hex[:16]


class DebateLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_data: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        session_id = session_id_context.get()
        trace_id = trace_id_context.get()
        stage = stage_context.get()
        span_id = span_id_context.get()
        parent_span_id = parent_span_id_context.get()
        span_name = span_name_context.get()

        if session_id:
            log_data["session_id"] = session_id
        if trace_id:
            log_data["trace_id"] = trace_id
        if stage:
            log_data["stage"] = stage
        if span_id:
            log_data["span_id"] = span_id
        if parent_span_id:
            log_data["parent_span_id"] = parent_span_id
        if span_name:
            log_data["span_name"] = span_name

        if hasattr(record, "extra"):
            log_data.update(record.extra)

        if record.exc_info:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": traceback.format_exception(*record.exc_info),
            }

        return json.dumps(log_data, ensure_ascii=False, default=str)


class DebateLogger:
    _instance: Optional["DebateLogger"] = None

    def __new__(cls) -> "DebateLogger":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return

        self._initialized = True
        self._setup_loggers()

    def _setup_loggers(self) -> None:
        self.logs_dir = settings.logs_dir
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_dir = self.logs_dir / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

        self.logger = logging.getLogger("debate")
        self.logger.setLevel(logging.DEBUG)
        self.logger.propagate = False
        self.logger.handlers.clear()

        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
        )
        self.logger.addHandler(console_handler)

        today = datetime.now(timezone.utc).strftime("%Y%m%d")

        file_handler = logging.FileHandler(self.logs_dir / f"debate_{today}.log", encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(DebateLogFormatter())
        self.logger.addHandler(file_handler)

        error_handler = logging.FileHandler(self.logs_dir / f"errors_{today}.log", encoding="utf-8")
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(DebateLogFormatter())
        self.logger.addHandler(error_handler)

        self._session_loggers: Dict[str, logging.Logger] = {}

    def _get_session_logger(self, session_id: str) -> logging.Logger:
        if session_id not in self._session_loggers:
            session_logger = logging.getLogger(f"debate.session.{session_id}")
            session_logger.setLevel(logging.DEBUG)
            session_logger.propagate = False
            session_logger.handlers.clear()

            file_handler = logging.FileHandler(self.sessions_dir / f"{session_id}.log", encoding="utf-8")
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(DebateLogFormatter())
            session_logger.addHandler(file_handler)

            self._session_loggers[session_id] = session_logger

        return self._session_loggers[session_id]

    def _log(
        self,
        level: int,
        message: str,
        extra: Optional[Dict[str, Any]] = None,
        exc_info: Optional[tuple] = None,
    ) -> None:
        extra_dict = {"extra": extra or {}}
        self.logger.log(level, message, exc_info=exc_info, extra=extra_dict)

        session_id = session_id_context.get()
        if session_id:
            session_logger = self._get_session_logger(session_id)
            session_logger.log(level, message, exc_info=exc_info, extra=extra_dict)

    def debug(self, message: str, **kwargs) -> None:
        self._log(logging.DEBUG, message, extra=kwargs)

    def info(self, message: str, **kwargs) -> None:
        self._log(logging.INFO, message, extra=kwargs)

    def warning(self, message: str, **kwargs) -> None:
        self._log(logging.WARNING, message, extra=kwargs)

    def error(self, message: str, exc: Optional[Exception] = None, **kwargs) -> None:
        exc_info = sys.exc_info() if exc else None
        self._log(logging.ERROR, message, exc_info=exc_info, extra=kwargs)

    def exception(self, message: str, **kwargs) -> None:
        self._log(logging.ERROR, message, exc_info=sys.exc_info(), extra=kwargs)

    def session_context(self, session_id: str, trace_id: Optional[str] = None):
        return _SessionContext(session_id, trace_id)

    def stage_context(self, stage: str):
        return _StageContext(stage)

    def span_context(self, span_name: str):
        return _SpanContext(span_name)

    def current_trace_context(self) -> Dict[str, Optional[str]]:
        return {
            "session_id": session_id_context.get(),
            "trace_id": trace_id_context.get(),
            "stage": stage_context.get(),
            "span_id": span_id_context.get(),
            "parent_span_id": parent_span_id_context.get(),
            "span_name": span_name_context.get(),
        }

    def session_created(self, session_id: str, topic: str, config: Dict[str, Any]) -> None:
        self.info(
            "Session created",
            event_type="session_created",
            session_id=session_id,
            topic=topic,
            config=config,
        )

    def session_state_changed(
        self,
        session_id: str,
        old_state: str,
        new_state: str,
        reason: Optional[str] = None,
    ) -> None:
        self.info(
            f"Session state changed: {old_state} -> {new_state}",
            event_type="session_state_changed",
            session_id=session_id,
            old_state=old_state,
            new_state=new_state,
            reason=reason,
        )

    def stage_start(self, stage: str, turn_id: int = 0, extra: Optional[Dict[str, Any]] = None) -> None:
        self.info(
            f"Stage started: {stage}",
            event_type="stage_start",
            stage=stage,
            turn_id=turn_id,
            **(extra or {}),
        )

    def stage_end(
        self,
        stage: str,
        duration_sec: float,
        turn_count: int = 0,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.info(
            f"Stage ended: {stage}",
            event_type="stage_end",
            stage=stage,
            duration_sec=duration_sec,
            turn_count=turn_count,
            **(extra or {}),
        )

    def turn_start(
        self,
        speaker: str,
        turn_id: int,
        stage: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.info(
            f"Turn started: {speaker} (turn {turn_id})",
            event_type="turn_start",
            speaker=speaker,
            turn_id=turn_id,
            stage=stage,
            **(extra or {}),
        )

    def turn_end(
        self,
        speaker: str,
        turn_id: int,
        duration_sec: float,
        token_count: int,
        content_length: int,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.info(
            f"Turn ended: {speaker} (turn {turn_id})",
            event_type="turn_end",
            speaker=speaker,
            turn_id=turn_id,
            duration_sec=duration_sec,
            token_count=token_count,
            content_length=content_length,
            **(extra or {}),
        )

    def llm_request(
        self,
        agent: str,
        operation: str,
        params: Dict[str, Any],
        prompt_length: Optional[int] = None,
    ) -> None:
        self.info(
            f"LLM request: {agent}.{operation}",
            event_type="llm_request",
            agent=agent,
            operation=operation,
            params=self._sanitize_params(params),
            prompt_length=prompt_length,
        )

    def llm_response(
        self,
        agent: str,
        operation: str,
        duration_sec: float,
        token_count: int,
        response_length: int,
        success: bool = True,
        error: Optional[str] = None,
    ) -> None:
        self.info(
            f"LLM response: {agent}.{operation} ({'success' if success else 'failed'})",
            event_type="llm_response",
            agent=agent,
            operation=operation,
            duration_sec=duration_sec,
            token_count=token_count,
            response_length=response_length,
            success=success,
            error=error,
        )

    def llm_stream_token(self, agent: str, turn_id: int, token_index: int, token: str) -> None:
        self.debug(
            f"LLM stream token: {agent}[{token_index}]",
            event_type="llm_stream_token",
            agent=agent,
            turn_id=turn_id,
            token_index=token_index,
            token=token[:50] if token else "",
        )

    def search_request(self, query: str, provider: str, num_results: int) -> None:
        self.info(
            f"Search request: {provider}",
            event_type="search_request",
            query=query,
            provider=provider,
            num_results=num_results,
        )

    def search_response(
        self,
        query: str,
        provider: str,
        duration_sec: float,
        result_count: int,
        success: bool = True,
        error: Optional[str] = None,
    ) -> None:
        self.info(
            f"Search response: {provider} ({'success' if success else 'failed'})",
            event_type="search_response",
            query=query,
            provider=provider,
            duration_sec=duration_sec,
            result_count=result_count,
            success=success,
            error=error,
        )

    def image_generation_request(self, image_type: str, params: Dict[str, Any]) -> None:
        self.info(
            f"Image generation request: {image_type}",
            event_type="image_generation_request",
            image_type=image_type,
            params=self._sanitize_params(params),
        )

    def image_generation_response(
        self,
        image_type: str,
        duration_sec: float,
        success: bool = True,
        error: Optional[str] = None,
        path: Optional[str] = None,
    ) -> None:
        self.info(
            f"Image generation response: {image_type} ({'success' if success else 'failed'})",
            event_type="image_generation_response",
            image_type=image_type,
            duration_sec=duration_sec,
            success=success,
            error=error,
            path=path,
        )

    def report_generated(self, session_id: str, path: str, duration_sec: float, total_turns: int) -> None:
        self.info(
            "Report generated",
            event_type="report_generated",
            session_id=session_id,
            path=path,
            duration_sec=duration_sec,
            total_turns=total_turns,
        )

    def follow_up_request(self, session_id: str, target_role: str, question: str) -> None:
        self.info(
            f"Follow-up request: {target_role}",
            event_type="follow_up_request",
            session_id=session_id,
            target_role=target_role,
            question=question[:200] if question else "",
        )

    def sse_event_sent(
        self,
        event_type: str,
        session_id: str,
        data_size: int,
        event_seq: int,
        source_span_id: Optional[str] = None,
        source_parent_span_id: Optional[str] = None,
    ) -> None:
        self.debug(
            f"SSE event sent: {event_type}",
            event_type="sse_event_sent",
            sse_event_type=event_type,
            session_id=session_id,
            data_size=data_size,
            event_seq=event_seq,
            source_span_id=source_span_id,
            source_parent_span_id=source_parent_span_id,
        )

    def heartbeat(self, session_id: str, stage: str, elapsed_sec: float) -> None:
        self.info(
            f"Heartbeat: {stage} running for {elapsed_sec:.1f}s",
            event_type="heartbeat",
            session_id=session_id,
            stage=stage,
            elapsed_sec=elapsed_sec,
        )

    def _sanitize_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        sensitive_keys = {"api_key", "token", "password", "secret"}
        sanitized = {}
        for key, value in params.items():
            if any(s in key.lower() for s in sensitive_keys):
                sanitized[key] = "***"
            elif isinstance(value, dict):
                sanitized[key] = self._sanitize_params(value)
            elif isinstance(value, str) and len(value) > 1000:
                sanitized[key] = value[:1000] + "... [truncated]"
            else:
                sanitized[key] = value
        return sanitized


class _SessionContext:
    def __init__(self, session_id: str, trace_id: Optional[str]) -> None:
        self.session_id = session_id
        self.trace_id = trace_id
        self.session_token = None
        self.trace_token = None
        self.span_token = None
        self.parent_span_token = None
        self.span_name_token = None
        self._own_root_span = False

    def __enter__(self):
        self.session_token = session_id_context.set(self.session_id)
        if self.trace_id:
            self.trace_token = trace_id_context.set(self.trace_id)
        elif trace_id_context.get() is None:
            self.trace_token = trace_id_context.set(self.session_id)

        if span_id_context.get() is None:
            self._own_root_span = True
            self.parent_span_token = parent_span_id_context.set(None)
            self.span_token = span_id_context.set(_new_span_id())
            self.span_name_token = span_name_context.set("session")

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._own_root_span:
            if self.span_name_token is not None:
                span_name_context.reset(self.span_name_token)
            if self.span_token is not None:
                span_id_context.reset(self.span_token)
            if self.parent_span_token is not None:
                parent_span_id_context.reset(self.parent_span_token)
        if self.trace_token is not None:
            trace_id_context.reset(self.trace_token)
        if self.session_token is not None:
            session_id_context.reset(self.session_token)


class _StageContext:
    def __init__(self, stage: str) -> None:
        self.stage = stage
        self.stage_token = None
        self.span_context = _SpanContext(f"stage:{stage}")

    def __enter__(self):
        self.stage_token = stage_context.set(self.stage)
        self.span_context.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.span_context.__exit__(exc_type, exc_val, exc_tb)
        if self.stage_token is not None:
            stage_context.reset(self.stage_token)


class _SpanContext:
    def __init__(self, span_name: str) -> None:
        self.span_name = span_name
        self.parent_span = None
        self.span_token = None
        self.parent_span_token = None
        self.span_name_token = None

    def __enter__(self):
        self.parent_span = span_id_context.get()
        self.parent_span_token = parent_span_id_context.set(self.parent_span)
        self.span_token = span_id_context.set(_new_span_id())
        self.span_name_token = span_name_context.set(self.span_name)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.span_name_token is not None:
            span_name_context.reset(self.span_name_token)
        if self.span_token is not None:
            span_id_context.reset(self.span_token)
        if self.parent_span_token is not None:
            parent_span_id_context.reset(self.parent_span_token)


def log_execution_time(operation_name: str):
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            logger = DebateLogger()
            start = datetime.now(timezone.utc)
            try:
                result = await func(*args, **kwargs)
                duration = (datetime.now(timezone.utc) - start).total_seconds()
                logger.debug(
                    f"Operation completed: {operation_name}",
                    event_type="operation_complete",
                    operation=operation_name,
                    duration_sec=duration,
                    success=True,
                )
                return result
            except Exception as exc:
                duration = (datetime.now(timezone.utc) - start).total_seconds()
                logger.error(
                    f"Operation failed: {operation_name}",
                    exc=exc,
                    event_type="operation_failed",
                    operation=operation_name,
                    duration_sec=duration,
                )
                raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            logger = DebateLogger()
            start = datetime.now(timezone.utc)
            try:
                result = func(*args, **kwargs)
                duration = (datetime.now(timezone.utc) - start).total_seconds()
                logger.debug(
                    f"Operation completed: {operation_name}",
                    event_type="operation_complete",
                    operation=operation_name,
                    duration_sec=duration,
                    success=True,
                )
                return result
            except Exception as exc:
                duration = (datetime.now(timezone.utc) - start).total_seconds()
                logger.error(
                    f"Operation failed: {operation_name}",
                    exc=exc,
                    event_type="operation_failed",
                    operation=operation_name,
                    duration_sec=duration,
                )
                raise

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator


debate_logger = DebateLogger()
