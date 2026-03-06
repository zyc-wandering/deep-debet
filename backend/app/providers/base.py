from __future__ import annotations

from typing import Iterable, List

from app.models import SearchResult


class LLMProvider:
    async def chat(self, system_prompt: str, user_prompt: str) -> str:
        raise NotImplementedError

    async def stream_chunks(self, text: str, chunk_size: int = 24) -> Iterable[str]:
        # Basic fallback stream adapter.
        for i in range(0, len(text), chunk_size):
            yield text[i : i + chunk_size]


class SearchProvider:
    async def search(self, query: str, num_results: int = 5) -> List[SearchResult]:
        raise NotImplementedError

