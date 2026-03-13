from __future__ import annotations

from newsstack.db import queries


async def get_news_by_region(
    state,
    region: str,
    hours: int = 24,
    limit: int = 50,
) -> list[dict]:
    """Get recent articles for a specific region."""
    articles = await queries.get_articles_by_region(
        state.db.conn, region=region, hours=hours, limit=limit
    )

    return [
        {
            "title": a.title,
            "summary": a.summary,
            "url": a.source_url,
            "source": a.source_feed,
            "category": a.category,
            "published_at": a.published_at.isoformat() if a.published_at else "",
            "cluster_id": a.cluster_id,
        }
        for a in articles
    ]
