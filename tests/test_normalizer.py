"""Tests for RSS/GDELT article normalization."""

from newsstack.ingestion.normalizer import normalize_rss_entry, normalize_gdelt_article, _clean_html


def test_normalize_rss_entry_basic():
    entry = {
        "link": "https://example.com/article",
        "title": "Test Article",
        "summary": "A brief summary",
        "published": "Thu, 13 Mar 2026 12:00:00 GMT",
    }
    article = normalize_rss_entry(entry, "TestFeed", "europe", "world")
    assert article is not None
    assert article.title == "Test Article"
    assert article.source_url == "https://example.com/article"
    assert article.source_feed == "TestFeed"
    assert article.region == "europe"
    assert article.category == "world"
    assert article.published_at is not None


def test_normalize_rss_entry_strips_html():
    entry = {
        "link": "https://example.com/html",
        "title": "<b>Bold Title</b>",
        "summary": "<p>Para with <a href='#'>link</a></p>",
    }
    article = normalize_rss_entry(entry, "Feed", "global", "general")
    assert article is not None
    assert "<" not in article.title
    assert "<" not in article.summary


def test_normalize_rss_entry_no_url_returns_none():
    entry = {"title": "No URL", "summary": "Missing link"}
    assert normalize_rss_entry(entry, "Feed", "global", "general") is None


def test_normalize_rss_entry_no_title_returns_none():
    entry = {"link": "https://example.com/notitle", "title": "", "summary": "Has summary"}
    assert normalize_rss_entry(entry, "Feed", "global", "general") is None


def test_normalize_gdelt_article_basic():
    art = {
        "url": "https://example.com/gdelt",
        "title": "GDELT Article",
        "seendate": "20260313T120000Z",
        "sourcecountry": "United States",
        "domain": "example.com",
    }
    article = normalize_gdelt_article(art)
    assert article is not None
    assert article.title == "GDELT Article"
    assert article.region == "north_america"
    assert article.source_feed == "gdelt"
    assert article.published_at is not None


def test_normalize_gdelt_article_unknown_country():
    art = {
        "url": "https://example.com/gdelt2",
        "title": "Article from nowhere",
        "seendate": "20260313T120000Z",
        "sourcecountry": "Narnia",
    }
    article = normalize_gdelt_article(art)
    assert article is not None
    assert article.region == "global"


def test_normalize_gdelt_no_url_returns_none():
    assert normalize_gdelt_article({"title": "No URL"}) is None


def test_normalize_gdelt_no_title_returns_none():
    assert normalize_gdelt_article({"url": "https://example.com/x", "title": ""}) is None


def test_clean_html():
    assert _clean_html("<p>Hello <b>world</b></p>") == "Hello world"
    assert _clean_html("  lots   of   spaces  ") == "lots of spaces"
    assert _clean_html("") == ""
