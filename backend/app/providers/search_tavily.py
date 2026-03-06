from __future__ import annotations

from typing import List

import httpx

from app.config import settings
from app.models import SearchResult
from app.providers.base import SearchProvider


class TavilySearchProvider(SearchProvider):
    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or settings.tavily_api_key

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    async def search(self, query: str, num_results: int = 5) -> List[SearchResult]:
        if not self.enabled:
            return []

        payload = {
            "api_key": self.api_key,
            "query": query,
            "max_results": max(1, min(10, num_results)),
            "search_depth": "advanced",
            "include_answer": False,
            "include_raw_content": False,
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post("https://api.tavily.com/search", json=payload)
            response.raise_for_status()
            body = response.json()

        results = []
        for item in body.get("results", []):
            results.append(
                SearchResult(
                    title=item.get("title", "Untitled"),
                    url=item.get("url", ""),
                    snippet=item.get("content", ""),
                    published_date=item.get("published_date"),
                )
            )
        return results

