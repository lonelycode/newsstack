"""Tests for embedding client — truncation, batching, error handling."""

import httpx
import pytest

from newsstack.processing.embeddings import EmbeddingClient

FAKE_URL = "http://fake:9097/v1/embeddings"
FAKE_REQUEST = httpx.Request("POST", FAKE_URL)


def _mock_embedding_response(n: int, dim: int = 768) -> httpx.Response:
    data = [{"index": i, "embedding": [0.1] * dim} for i in range(n)]
    return httpx.Response(200, json={"data": data}, request=FAKE_REQUEST)


@pytest.mark.asyncio
async def test_embed_truncates_long_text():
    """Text should be truncated to max_chars before sending."""
    client = EmbeddingClient(FAKE_URL, "test-model", max_chars=100)
    sent_payloads = []

    async def mock_post(url, json=None, timeout=None):
        sent_payloads.append(json)
        return _mock_embedding_response(1)

    mock_http = httpx.AsyncClient()
    mock_http.post = mock_post

    long_text = "x" * 5000
    result = await client.embed([long_text], mock_http)

    assert len(result) == 1
    assert len(sent_payloads[0]["input"][0]) == 100


@pytest.mark.asyncio
async def test_embed_sends_one_at_a_time():
    """Each text should be sent individually, not batched."""
    client = EmbeddingClient(FAKE_URL, "test-model")
    call_count = 0

    async def mock_post(url, json=None, timeout=None):
        nonlocal call_count
        call_count += 1
        return _mock_embedding_response(len(json["input"]))

    mock_http = httpx.AsyncClient()
    mock_http.post = mock_post

    texts = ["text1", "text2", "text3"]
    result = await client.embed(texts, mock_http)

    assert len(result) == 3
    assert call_count == 3


@pytest.mark.asyncio
async def test_embed_empty_list():
    client = EmbeddingClient(FAKE_URL, "test-model")
    result = await client.embed([], httpx.AsyncClient())
    assert result == []


@pytest.mark.asyncio
async def test_embed_single():
    client = EmbeddingClient(FAKE_URL, "test-model", max_chars=50)
    sent_payloads = []

    async def mock_post(url, json=None, timeout=None):
        sent_payloads.append(json)
        return _mock_embedding_response(1)

    mock_http = httpx.AsyncClient()
    mock_http.post = mock_post

    result = await client.embed_single("a" * 200, mock_http)
    assert len(result) == 768
    assert len(sent_payloads[0]["input"][0]) == 50


@pytest.mark.asyncio
async def test_embed_preserves_order():
    client = EmbeddingClient(FAKE_URL, "test-model")
    call_index = 0

    async def mock_post(url, json=None, timeout=None):
        nonlocal call_index
        embedding = [float(call_index)] * 768
        call_index += 1
        return httpx.Response(
            200,
            json={"data": [{"index": 0, "embedding": embedding}]},
            request=FAKE_REQUEST,
        )

    mock_http = httpx.AsyncClient()
    mock_http.post = mock_post

    result = await client.embed(["a", "b", "c"], mock_http)
    assert result[0][0] == 0.0
    assert result[1][0] == 1.0
    assert result[2][0] == 2.0
