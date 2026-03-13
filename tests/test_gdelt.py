"""Tests for GDELT API client — response parsing and error handling."""

import httpx
import pytest

from newsstack.ingestion.gdelt import fetch_gdelt_articles

FAKE_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
FAKE_REQUEST = httpx.Request("GET", FAKE_URL)


@pytest.mark.asyncio
async def test_gdelt_empty_response():
    """GDELT sometimes returns 200 with empty body."""
    async def mock_get(url, params=None, timeout=None):
        return httpx.Response(200, text="", request=FAKE_REQUEST)

    mock_http = httpx.AsyncClient()
    mock_http.get = mock_get

    result = await fetch_gdelt_articles(mock_http)
    assert result == []


@pytest.mark.asyncio
async def test_gdelt_non_json_response():
    """GDELT sometimes returns HTML error pages with 200 status."""
    async def mock_get(url, params=None, timeout=None):
        return httpx.Response(200, text="<html><body>Rate limited</body></html>", request=FAKE_REQUEST)

    mock_http = httpx.AsyncClient()
    mock_http.get = mock_get

    result = await fetch_gdelt_articles(mock_http)
    assert result == []


@pytest.mark.asyncio
async def test_gdelt_valid_response():
    payload = {
        "articles": [
            {
                "url": "https://example.com/news1",
                "title": "Test Article",
                "seendate": "20260313T120000Z",
                "sourcecountry": "United Kingdom",
                "domain": "example.com",
            },
            {
                "url": "https://example.com/news2",
                "title": "Another Article",
                "seendate": "20260313T130000Z",
                "sourcecountry": "France",
                "domain": "example.fr",
            },
        ]
    }

    async def mock_get(url, params=None, timeout=None):
        return httpx.Response(200, json=payload, request=FAKE_REQUEST)

    mock_http = httpx.AsyncClient()
    mock_http.get = mock_get

    result = await fetch_gdelt_articles(mock_http)
    assert len(result) == 2
    assert result[0].title == "Test Article"
    assert result[0].region == "europe"


@pytest.mark.asyncio
async def test_gdelt_http_error():
    async def mock_get(url, params=None, timeout=None):
        return httpx.Response(429, text="Rate limited", request=FAKE_REQUEST)

    mock_http = httpx.AsyncClient()
    mock_http.get = mock_get

    result = await fetch_gdelt_articles(mock_http)
    assert result == []


@pytest.mark.asyncio
async def test_gdelt_no_articles_key():
    async def mock_get(url, params=None, timeout=None):
        return httpx.Response(200, json={}, request=FAKE_REQUEST)

    mock_http = httpx.AsyncClient()
    mock_http.get = mock_get

    result = await fetch_gdelt_articles(mock_http)
    assert result == []
