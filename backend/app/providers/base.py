from __future__ import annotations

from typing import AsyncGenerator, List

from app.models import SearchResult


class LLMProvider:
    """Abstract LLM provider interface.

    Subclasses must implement :meth:`chat_stream`.
    :meth:`chat` has a default implementation that collects the stream.
    """

    async def chat(self, system_prompt: str, user_prompt: str) -> str:
        """Return the complete response as a single string."""
        parts: list[str] = []
        async for token in self.chat_stream(system_prompt, user_prompt):
            parts.append(token)
        return "".join(parts).strip()

    async def chat_stream(
        self, system_prompt: str, user_prompt: str
    ) -> AsyncGenerator[str, None]:
        """Stream tokens from the LLM. Must be overridden by subclasses."""
        raise NotImplementedError
        yield  # make this a generator


class SearchProvider:
    async def search(self, query: str, num_results: int = 5) -> List[SearchResult]:
        raise NotImplementedError
