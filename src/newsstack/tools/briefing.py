from __future__ import annotations

from newsstack.db import queries


async def get_topic_briefing(
    state,
    topic: str,
    hours: int = 48,
    max_articles: int = 10,
) -> dict:
    """Generate an intelligence briefing on a topic using semantic search + LLM."""
    # Embed the topic
    query_vector = await state.embedding_client.embed_single(topic, state.http_client)

    # Find relevant articles
    results = await state.vector_store.search(
        vector=query_vector,
        limit=max_articles,
        score_threshold=0.3,
    )

    if not results:
        return {"topic": topic, "briefing": "No relevant articles found.", "articles": []}

    ids = [r[0] for r in results]
    articles = await queries.get_articles_by_ids(state.db.conn, ids)

    # Build article text for LLM
    articles_text = "\n\n".join(
        f"Title: {a.title}\nSource: {a.source_feed}\nSummary: {a.summary}"
        for a in articles
    )

    # Generate briefing
    briefing = ""
    if state.summarizer:
        briefing = await state.summarizer.generate_briefing(
            topic, articles_text, state.http_client
        )

    return {
        "topic": topic,
        "briefing": briefing,
        "article_count": len(articles),
        "sources": list({a.source_feed for a in articles}),
        "articles": [
            {
                "title": a.title,
                "url": a.source_url,
                "source": a.source_feed,
                "published_at": a.published_at.isoformat() if a.published_at else "",
            }
            for a in articles
        ],
    }
