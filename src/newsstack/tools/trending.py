from __future__ import annotations

from newsstack.db import queries


async def get_trending_topics(
    state,
    hours: int = 12,
    limit: int = 10,
) -> list[dict]:
    """Get trending topics based on cluster size and velocity."""
    clusters = await queries.get_top_clusters(state.db.conn, hours=hours, limit=limit)

    results = []
    for cluster in clusters:
        articles = await queries.get_articles_by_cluster(state.db.conn, cluster.id)
        sources = list({a.source_feed for a in articles})
        regions = list({a.region for a in articles if a.region})

        results.append({
            "cluster_id": cluster.id,
            "topic": cluster.label,
            "summary": cluster.summary,
            "article_count": cluster.article_count,
            "sources": sources,
            "regions": regions,
            "latest_published": max(
                (a.published_at.isoformat() for a in articles if a.published_at),
                default="",
            ),
        })

    # Fall back to recent articles grouped by source if no clusters yet
    if not results:
        articles = await queries.get_recent_articles(state.db.conn, hours=hours, limit=limit * 3)
        # Group by category as pseudo-topics
        by_category: dict[str, list] = {}
        for a in articles:
            cat = a.category or "general"
            by_category.setdefault(cat, []).append(a)

        for cat, cat_articles in sorted(by_category.items(), key=lambda x: -len(x[1])):
            results.append({
                "topic": f"{cat} news",
                "summary": cat_articles[0].title if cat_articles else "",
                "article_count": len(cat_articles),
                "sources": list({a.source_feed for a in cat_articles}),
                "regions": list({a.region for a in cat_articles if a.region}),
                "latest_published": max(
                    (a.published_at.isoformat() for a in cat_articles if a.published_at),
                    default="",
                ),
            })

    return results[:limit]
