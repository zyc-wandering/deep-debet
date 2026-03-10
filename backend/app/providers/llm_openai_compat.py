from __future__ import annotations

import json
from typing import Any, AsyncGenerator, Dict, List

import httpx

from app.config import settings
from app.providers.base import LLMProvider


class OpenAICompatProvider(LLMProvider):
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        api_style: str = "chat_completions",
        response_tools: List[Dict[str, Any]] | None = None,
    ) -> None:
        self.base_url = (base_url or settings.openai_base_url).rstrip("/")
        self.api_key = api_key or settings.openai_api_key
        self.model = model or settings.openai_model
        self.api_style = api_style
        self.response_tools = response_tools or []

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    async def chat_stream(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> AsyncGenerator[str, None]:
        """Stream chat completion from LLM, yielding tokens as they arrive."""
        if not self.enabled:
            raise RuntimeError("OPENAI_API_KEY is missing")

        if self.api_style == "responses":
            async for token in self._responses_stream(system_prompt, user_prompt):
                yield token
            return

        payload: Dict[str, Any] = {
            "model": self.model,
            "temperature": 0.8,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": True,
        }
        if "api.kimi.com/coding" in self.base_url:
            payload["max_tokens"] = settings.openai_max_output_tokens

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        url = f"{self.base_url}/chat/completions"

        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    detail = await response.aread()
                    detail_text = detail.decode("utf-8", errors="ignore")
                    raise RuntimeError(
                        f"LLM stream request failed with status {response.status_code}: {detail_text[:500]}"
                    ) from exc

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
                                yield content
                        except json.JSONDecodeError:
                            continue

    async def chat(self, system_prompt: str, user_prompt: str) -> str:
        if not self.enabled:
            raise RuntimeError("OPENAI_API_KEY is missing")

        if self.api_style == "responses":
            parts = []
            async for token in self._responses_stream(system_prompt, user_prompt):
                parts.append(token)
            return "".join(parts).strip()

        payload: Dict[str, Any] = {
            "model": self.model,
            "temperature": 0.8,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if "api.kimi.com/coding" in self.base_url:
            payload["max_tokens"] = settings.openai_max_output_tokens

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        url = f"{self.base_url}/chat/completions"
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(url, headers=headers, json=payload)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = response.text.strip()
                if not detail:
                    detail = json.dumps(response.json(), ensure_ascii=False)
                if "only available for Coding Agents" in detail:
                    raise RuntimeError(
                        "Kimi Code API keys are limited to approved coding agents. "
                        "For this debate app, use a Moonshot Open Platform or other standard OpenAI-compatible API key."
                    ) from exc
                if "insufficient balance" in detail or "exceeded_current_quota_error" in detail:
                    raise RuntimeError(
                        "Moonshot API request was rejected because the account has insufficient balance or quota. "
                        "Recharge the Moonshot account or switch to another active API key."
                    ) from exc
                raise RuntimeError(
                    f"LLM request failed with status {response.status_code} at {url}: {detail[:500]}"
                ) from exc
            body = response.json()

        choice = (body.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        content = message.get("content", "")
        if isinstance(content, list):
            parts = [part.get("text", "") for part in content if isinstance(part, dict)]
            content = "".join(parts)
        return str(content).strip()

    async def _responses_stream(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> AsyncGenerator[str, None]:
        payload: Dict[str, Any] = {
            "model": self.model,
            "stream": True,
            "input": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": user_prompt,
                        }
                    ],
                }
            ],
        }
        if system_prompt.strip():
            payload["instructions"] = system_prompt
        if self.response_tools:
            payload["tools"] = self.response_tools

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        url = f"{self.base_url}/responses"
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    detail = await response.aread()
                    detail_text = detail.decode("utf-8", errors="ignore")
                    raise RuntimeError(
                        f"LLM responses stream request failed with status {response.status_code}: {detail_text[:500]}"
                    ) from exc

                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line or line.startswith(":") or line.startswith("event:"):
                        continue
                    if not line.startswith("data: "):
                        continue

                    data = line[6:]
                    if data == "[DONE]":
                        break

                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue

                    event_type = chunk.get("type", "")
                    if event_type == "response.output_text.delta":
                        delta = chunk.get("delta", "")
                        if delta:
                            yield delta
                        continue

                    if event_type == "error":
                        message = (chunk.get("error") or {}).get("message") or chunk.get("message") or "Unknown error"
                        raise RuntimeError(f"LLM responses stream failed: {message}")

                    if event_type in {"response.completed", "response.failed", "response.incomplete"}:
                        if event_type != "response.completed":
                            message = (
                                ((chunk.get("response") or {}).get("error") or {}).get("message")
                                or ((chunk.get("response") or {}).get("incomplete_details") or {}).get("reason")
                                or event_type
                            )
                            raise RuntimeError(f"LLM responses stream ended early: {message}")
                        break
