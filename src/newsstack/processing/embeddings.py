from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

class EmbeddingClient:
    def __init__(self, url: str, model: str, max_chars: int = 1500) -> None:
        self.url = url
        self.model = model
        self.max_chars = max_chars

    async def embed(self, texts: list[str], client: httpx.AsyncClient) -> list[list[float]]:
        """Get embeddings one at a time, truncating to fit the server's token limit."""
        if not texts:
            return []

        all_embeddings: list[list[float]] = []
        for text in texts:
            embedding = await self._embed_one(text, client)
            all_embeddings.append(embedding)

        return all_embeddings

    async def _embed_one(self, text: str, client: httpx.AsyncClient) -> list[float]:
        text = text[:self.max_chars]
        results = await self._embed_batch([text], client)
        return results[0]

    async def _embed_batch(self, texts: list[str], client: httpx.AsyncClient) -> list[list[float]]:
        payload = {
            "input": texts,
            "model": self.model,
        }

        try:
            resp = await client.post(self.url, json=payload, timeout=60.0)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.error("Embedding request failed: %s", e)
            raise

        data = resp.json()
        sorted_data = sorted(data["data"], key=lambda x: x["index"])
        return [item["embedding"] for item in sorted_data]

    async def embed_single(self, text: str, client: httpx.AsyncClient) -> list[float]:
        return await self._embed_one(text, client)
