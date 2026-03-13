from __future__ import annotations

import logging
from datetime import datetime

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    Range,
    SearchParams,
    VectorParams,
)

logger = logging.getLogger(__name__)

COLLECTION = "news_articles"


class VectorStore:
    def __init__(self, url: str, embedding_dim: int = 768) -> None:
        self.client = AsyncQdrantClient(url=url)
        self.embedding_dim = embedding_dim

    async def setup(self) -> None:
        collections = await self.client.get_collections()
        names = [c.name for c in collections.collections]
        if COLLECTION not in names:
            await self.client.create_collection(
                collection_name=COLLECTION,
                vectors_config=VectorParams(
                    size=self.embedding_dim, distance=Distance.COSINE
                ),
            )
            for field_name, schema_type in [
                ("source_feed", PayloadSchemaType.KEYWORD),
                ("region", PayloadSchemaType.KEYWORD),
                ("published_at", PayloadSchemaType.KEYWORD),
                ("cluster_id", PayloadSchemaType.KEYWORD),
            ]:
                await self.client.create_payload_index(
                    collection_name=COLLECTION,
                    field_name=field_name,
                    field_schema=schema_type,
                )
            logger.info("Created Qdrant collection '%s'", COLLECTION)

    async def reset(self) -> None:
        """Drop and recreate the collection."""
        collections = await self.client.get_collections()
        names = [c.name for c in collections.collections]
        if COLLECTION in names:
            await self.client.delete_collection(COLLECTION)
            logger.info("Deleted Qdrant collection '%s'", COLLECTION)
        await self.setup()

    async def count(self) -> int:
        """Return the number of points in the collection."""
        info = await self.client.get_collection(COLLECTION)
        return info.points_count or 0

    async def upsert(
        self,
        article_id: str,
        vector: list[float],
        source_feed: str = "",
        region: str = "",
        published_at: str = "",
        cluster_id: str | None = None,
    ) -> None:
        payload: dict = {
            "source_feed": source_feed,
            "region": region,
            "published_at": published_at,
        }
        if cluster_id:
            payload["cluster_id"] = cluster_id
        await self.client.upsert(
            collection_name=COLLECTION,
            points=[
                PointStruct(id=article_id, vector=vector, payload=payload)
            ],
        )

    async def search(
        self,
        vector: list[float],
        limit: int = 20,
        score_threshold: float = 0.0,
        region: str | None = None,
        source_feed: str | None = None,
        since: datetime | None = None,
    ) -> list[tuple[str, float]]:
        """Search for similar articles. Returns list of (id, score)."""
        conditions = []
        if region:
            conditions.append(
                FieldCondition(key="region", match=MatchValue(value=region))
            )
        if source_feed:
            conditions.append(
                FieldCondition(key="source_feed", match=MatchValue(value=source_feed))
            )
        if since:
            conditions.append(
                FieldCondition(
                    key="published_at",
                    range=Range(gte=since.isoformat()),
                )
            )

        query_filter = Filter(must=conditions) if conditions else None

        response = await self.client.query_points(
            collection_name=COLLECTION,
            query=vector,
            limit=limit,
            score_threshold=score_threshold,
            query_filter=query_filter,
            search_params=SearchParams(exact=False, hnsw_ef=128),
        )
        return [(str(point.id), point.score) for point in response.points]

    async def get_vectors(self, ids: list[str]) -> dict[str, list[float]]:
        """Retrieve vectors by IDs."""
        if not ids:
            return {}
        points = await self.client.retrieve(
            collection_name=COLLECTION,
            ids=ids,
            with_vectors=True,
        )
        return {
            str(p.id): p.vector
            for p in points
            if p.vector is not None
        }

    async def delete(self, ids: list[str]) -> None:
        if ids:
            await self.client.delete(
                collection_name=COLLECTION,
                points_selector=ids,
            )

    async def close(self) -> None:
        await self.client.close()
