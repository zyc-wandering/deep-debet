from __future__ import annotations

import json
from typing import Any, Dict

import httpx

from app.config import settings
from app.providers.base import LLMProvider


class OpenAICompatProvider(LLMProvider):
    def __init__(self, base_url: str | None = None, api_key: str | None = None, model: str | None = None) -> None:
        self.base_url = (base_url or settings.openai_base_url).rstrip("/")
        self.api_key = api_key or settings.openai_api_key
        self.model = model or settings.openai_model

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    async def chat(self, system_prompt: str, user_prompt: str) -> str:
        if not self.enabled:
            raise RuntimeError("OPENAI_API_KEY is missing")

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
