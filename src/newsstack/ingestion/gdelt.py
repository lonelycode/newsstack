from __future__ import annotations

import logging

import httpx

from newsstack.db.models import Article
from newsstack.ingestion.normalizer import normalize_gdelt_article

logger = logging.getLogger(__name__)

GDELT_DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"


async def fetch_gdelt_articles(
    client: httpx.AsyncClient,
    query: str = "",
    mode: str = "ArtList",
    max_records: int = 75,
    timespan: str = "15min",
) -> list[Article]:
    """Fetch recent articles from GDELT DOC API."""
    params: dict[str, str] = {
        "format": "json",
        "mode": mode,
        "maxrecords": str(max_records),
        "timespan": timespan,
        "sort": "DateDesc",
    }
    if query:
        params["query"] = query
    else:
        params["query"] = "sourcelang:english"

    try:
        resp = await client.get(GDELT_DOC_API, params=params, timeout=30.0)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        logger.warning("GDELT API error: %s", e)
        return []

    text = resp.text.strip()
    if not text:
        logger.warning("GDELT returned empty response")
        return []

    try:
        data = resp.json()
    except Exception:
        logger.warning("GDELT returned non-JSON response: %s", text[:200])
        return []

    raw_articles = data.get("articles", [])

    articles: list[Article] = []
    for raw in raw_articles:
        article = normalize_gdelt_article(raw)
        if article:
            articles.append(article)

    logger.info("Fetched %d articles from GDELT", len(articles))
    return articles
