from __future__ import annotations

import logging

from simhash import Simhash

from newsstack.db.models import Article

logger = logging.getLogger(__name__)


def compute_simhash(text: str) -> int:
    """Compute a 64-bit SimHash for near-duplicate detection."""
    return Simhash(text).value


def hamming_distance(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def filter_simhash_dupes(
    articles: list[Article],
    existing_hashes: list[tuple[str, int]],
    threshold: int = 3,
) -> list[Article]:
    """Remove articles that are near-duplicates of existing articles (by SimHash)."""
    kept: list[Article] = []
    # Build set of existing hashes for comparison
    all_hashes: list[tuple[str, int]] = list(existing_hashes)

    for article in articles:
        text = f"{article.title} {article.summary}"
        sh = compute_simhash(text)
        article.simhash = sh

        is_dupe = False
        for _, existing_sh in all_hashes:
            if hamming_distance(sh, existing_sh) <= threshold:
                is_dupe = True
                break

        if not is_dupe:
            kept.append(article)
            all_hashes.append((article.id, sh))
        else:
            logger.debug("SimHash duplicate: %s", article.title[:80])

    return kept


async def filter_vector_dupes(
    articles: list[Article],
    embeddings: list[list[float]],
    vector_store,
    threshold: float = 0.95,
) -> tuple[list[Article], list[list[float]]]:
    """Remove articles whose embeddings are too similar to existing vectors."""
    kept_articles: list[Article] = []
    kept_embeddings: list[list[float]] = []

    for article, embedding in zip(articles, embeddings):
        results = await vector_store.search(
            vector=embedding,
            limit=1,
            score_threshold=threshold,
        )
        if results:
            logger.debug("Vector duplicate (score=%.3f): %s", results[0][1], article.title[:80])
        else:
            kept_articles.append(article)
            kept_embeddings.append(embedding)

    return kept_articles, kept_embeddings
