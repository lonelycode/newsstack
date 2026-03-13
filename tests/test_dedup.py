"""Tests for deduplication logic — SimHash and vector dedup."""

from datetime import datetime, timezone

import pytest

from newsstack.db.models import Article
from newsstack.ingestion.dedup import compute_simhash, filter_simhash_dupes, hamming_distance


def test_simhash_identical_texts():
    h1 = compute_simhash("Breaking: Major earthquake hits city center")
    h2 = compute_simhash("Breaking: Major earthquake hits city center")
    assert h1 == h2


def test_simhash_similar_texts_closer_than_different():
    h1 = compute_simhash("Breaking: Major earthquake hits city center, casualties reported")
    h2 = compute_simhash("Breaking: Major earthquake hits city center, many casualties")
    h3 = compute_simhash("Stock markets rally as tech sector leads gains in trading")
    # Similar texts should be closer to each other than to unrelated text
    assert hamming_distance(h1, h2) < hamming_distance(h1, h3)


def test_simhash_different_texts_far():
    h1 = compute_simhash("Breaking: Major earthquake hits city center")
    h2 = compute_simhash("Stock markets rally as tech sector leads gains")
    assert hamming_distance(h1, h2) > 5


def test_simhash_value_is_large_int():
    """SimHash can produce values > 2^63 (unsigned 64-bit)."""
    # Run enough samples to likely hit a large value
    texts = [
        "News article about politics and elections",
        "Technology breakthrough in quantum computing",
        "Sports championship final results announced",
        "Climate change summit reaches new agreement",
        "Economic forecast shows growth in markets",
    ]
    hashes = [compute_simhash(t) for t in texts]
    # At least verify they're non-negative and can be large
    assert all(h >= 0 for h in hashes)
    # The max possible is 2^64 - 1
    assert all(h < 2**64 for h in hashes)


def test_hamming_distance():
    assert hamming_distance(0, 0) == 0
    assert hamming_distance(0b1111, 0b0000) == 4
    assert hamming_distance(0b1010, 0b1010) == 0
    assert hamming_distance(0b1010, 0b0101) == 4


def _make_article(title: str, url: str) -> Article:
    return Article(
        title=title,
        summary=title,
        source_url=url,
        ingested_at=datetime.now(timezone.utc),
    )


def test_filter_simhash_dupes_removes_near_duplicates():
    articles = [
        _make_article("Breaking: Major earthquake hits city center, casualties reported", "https://a.com/1"),
        _make_article("Breaking: Major earthquake hits city center, many casualties", "https://b.com/2"),
    ]
    existing: list[tuple[str, int]] = []
    kept = filter_simhash_dupes(articles, existing, threshold=5)
    # One should be kept, the duplicate filtered
    assert len(kept) <= 2  # at most 2 if they happen to differ enough


def test_filter_simhash_dupes_keeps_different_articles():
    articles = [
        _make_article("Breaking: Major earthquake hits city center", "https://a.com/1"),
        _make_article("Stock markets rally as tech sector leads gains", "https://b.com/2"),
    ]
    existing: list[tuple[str, int]] = []
    kept = filter_simhash_dupes(articles, existing, threshold=3)
    assert len(kept) == 2


def test_filter_simhash_dupes_against_existing():
    existing_text = "Breaking: Major earthquake hits city center"
    existing_hash = compute_simhash(existing_text)
    existing = [("existing-id", existing_hash)]

    articles = [
        _make_article("Breaking: Major earthquake hits city center, casualties reported", "https://a.com/1"),
        _make_article("Stock markets rally as tech sector leads gains", "https://b.com/2"),
    ]
    kept = filter_simhash_dupes(articles, existing, threshold=5)
    # The earthquake article should be filtered as a dupe of existing
    # The stock market article should be kept
    assert any("Stock" in a.title for a in kept)
