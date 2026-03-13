from __future__ import annotations

from newsstack.db import queries


async def get_latest_headlines(
    state,
    hours: int = 24,
    limit: int = 20,
    category: str | None = None,
) -> list[dict]:
    """Get the latest headlines — clustered stories first, then unclustered articles."""
    results = []

    # Try clusters first
    clusters = await queries.get_top_clusters(state.db.conn, hours=hours, limit=limit)
    for cluster in clusters:
        articles = await queries.get_articles_by_cluster(state.db.conn, cluster.id)
        sources = list({a.source_feed for a in articles})

        if category and not any(a.category == category for a in articles):
            continue

        results.append({
            "cluster_id": cluster.id,
            "headline": cluster.label,
            "summary": cluster.summary,
            "article_count": cluster.article_count,
            "sources": sources,
            "latest_published": max(
                (a.published_at.isoformat() for a in articles if a.published_at),
                default="",
            ),
            "articles": [
                {
                    "title": a.title,
                    "url": a.source_url,
                    "source": a.source_feed,
                    "published_at": a.published_at.isoformat() if a.published_at else "",
                }
                for a in articles[:5]
            ],
        })

    # If no clusters yet, fall back to recent individual articles
    if not results:
        articles = await queries.get_recent_articles(
            state.db.conn, hours=hours, limit=limit, category=category
        )
        for a in articles:
            results.append({
                "headline": a.title,
                "summary": a.summary,
                "article_count": 1,
                "sources": [a.source_feed],
                "latest_published": a.published_at.isoformat() if a.published_at else "",
                "articles": [
                    {
                        "title": a.title,
                        "url": a.source_url,
                        "source": a.source_feed,
                        "published_at": a.published_at.isoformat() if a.published_at else "",
                    }
                ],
            })

    return results[:limit]
