from __future__ import annotations

from typing import List

import httpx

from app.config import settings
from app.models import SearchResult
from app.providers.base import SearchProvider


class PerplexitySearchProvider(SearchProvider):
    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or settings.perplexity_api_key

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    async def search(self, query: str, num_results: int = 5) -> List[SearchResult]:
        if not self.enabled:
            return []

        payload = {
            "query": query,
            "max_results": max(1, min(20, num_results)),
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://api.perplexity.ai/search",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            body = response.json()

        results = []
        for item in body.get("results", []):
            results.append(
                SearchResult(
                    title=item.get("title", "Untitled"),
                    url=item.get("url", ""),
                    snippet=item.get("snippet", ""),
                    published_date=item.get("date"),
                )
            )
        return results
