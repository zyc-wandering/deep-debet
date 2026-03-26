from __future__ import annotations

import json
from time import monotonic
from typing import Any, AsyncGenerator, Dict

import httpx

from app.config import settings
from app.providers.base import LLMProvider
from app.utils.logger import debate_logger


class ContentFilterError(RuntimeError):
    """Raised when the LLM provider rejects a request due to content safety filters."""
    pass


# ---------------------------------------------------------------------------
# Timeout strategy:
#   connect  = 30 s   – TCP + TLS handshake
#   read     = 180 s  – max gap *between* successive SSE chunks
#   write    = 30 s   – sending the request body
#   pool     = 30 s   – waiting for a connection from the pool
# Because we always use `stream=True`, the read timeout only governs the
# interval between two chunks, NOT the total generation time.
# ---------------------------------------------------------------------------
_TIMEOUT = httpx.Timeout(connect=30.0, read=180.0, write=30.0, pool=30.0)


class OpenAICompatProvider(LLMProvider):
    """Unified OpenAI-compatible LLM provider.

    Works identically with any provider that implements the
    ``/chat/completions`` endpoint (Ark, GLM / Zhipu, Moonshot, OpenAI …).
    Callers only need to supply ``base_url``, ``api_key``, ``model``.
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self.base_url = (base_url or settings.openai_base_url).rstrip("/")
        self.api_key = api_key or settings.openai_api_key
        self.model = model or settings.openai_model

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    # ------------------------------------------------------------------
    # Streaming chat  (the single source of truth for all LLM calls)
    # ------------------------------------------------------------------

    async def chat_stream(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> AsyncGenerator[str, None]:
        """Stream chat completion, yielding tokens as they arrive.

        Uses the standard OpenAI ``/chat/completions`` SSE protocol which is
        supported by Ark, GLM, Moonshot, OpenAI, and others.
        """
        stream_start = monotonic()
        if not self.enabled:
            raise RuntimeError("LLM API key is not configured")

        debate_logger.debug(
            "Provider chat_stream request",
            event_type="provider_llm_stream_request",
            model=self.model,
            prompt_length=len(user_prompt),
            base_url=self.base_url,
        )

        payload: Dict[str, Any] = {
            "model": self.model,
            "temperature": 0.8,
            "max_tokens": settings.openai_max_output_tokens,
            "stream": True,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        url = f"{self.base_url}/chat/completions"

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    detail = await response.aread()
                    detail_text = detail.decode("utf-8", errors="replace")
                    if '"code":"1301"' in detail_text or "contentFilter" in detail_text:
                        raise ContentFilterError(
                            "LLM provider rejected the request due to content safety filters. "
                            "Try rephrasing the topic to avoid sensitive content."
                        ) from exc
                    raise RuntimeError(
                        f"LLM request failed [{response.status_code}]: {detail_text[:500]}"
                    ) from exc

                token_count = 0
                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line or line.startswith(":"):
                        continue
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                token_count += 1
                                yield content
                        except json.JSONDecodeError:
                            continue

                debate_logger.debug(
                    "Provider chat_stream completed",
                    event_type="provider_llm_stream_complete",
                    model=self.model,
                    token_count=token_count,
                    duration_sec=monotonic() - stream_start,
                )

    # ------------------------------------------------------------------
    # Non-streaming chat  (collects stream internally)
    # ------------------------------------------------------------------

    async def chat(self, system_prompt: str, user_prompt: str) -> str:
        """Return complete LLM response as a single string.

        Internally delegates to :meth:`chat_stream` so the httpx read-timeout
        only guards the gap between successive chunks, not total generation.
        """
        chat_start = monotonic()
        if not self.enabled:
            raise RuntimeError("LLM API key is not configured")

        parts: list[str] = []
        async for token in self.chat_stream(system_prompt, user_prompt):
            parts.append(token)
        content = "".join(parts).strip()

        debate_logger.debug(
            "Provider chat completed (via stream collect)",
            event_type="provider_llm_chat_complete",
            model=self.model,
            response_length=len(content),
            duration_sec=monotonic() - chat_start,
        )
        return content
