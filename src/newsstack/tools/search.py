from __future__ import annotations

from datetime import datetime, timezone

from newsstack.db import queries


async def search_news(
    state,
    query: str,
    limit: int = 20,
    region: str | None = None,
    hours: int | None = None,
) -> list[dict]:
    """Semantic search over news articles."""
    # Embed the query
    query_vector = await state.embedding_client.embed_single(query, state.http_client)

    since = None
    if hours:
        from datetime import timedelta
        since = datetime.now(timezone.utc) - timedelta(hours=hours)

    # Search Qdrant
    results = await state.vector_store.search(
        vector=query_vector,
        limit=limit,
        region=region,
        since=since,
    )

    if not results:
        return []

    # Get articles from SQLite
    ids = [r[0] for r in results]
    scores = {r[0]: r[1] for r in results}
    articles = await queries.get_articles_by_ids(state.db.conn, ids)

    return [
        {
            "title": a.title,
            "summary": a.summary,
            "url": a.source_url,
            "source": a.source_feed,
            "region": a.region,
            "category": a.category,
            "published_at": a.published_at.isoformat() if a.published_at else "",
            "relevance_score": round(scores.get(a.id, 0.0), 4),
            "cluster_id": a.cluster_id,
        }
        for a in articles
    ]
