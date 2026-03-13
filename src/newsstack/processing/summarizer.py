from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


class Summarizer:
    def __init__(self, url: str, model: str) -> None:
        self.url = url
        self.model = model

    async def summarize_cluster(
        self, titles: list[str], client: httpx.AsyncClient
    ) -> str:
        """Generate a brief summary for a cluster of related articles."""
        titles_text = "\n".join(f"- {t}" for t in titles[:15])
        prompt = (
            "Below are headlines from related news articles about the same story. "
            "Write a concise 2-3 sentence summary of the overall story.\n\n"
            f"{titles_text}"
        )
        return await self._complete(prompt, client)

    async def generate_briefing(
        self, topic: str, articles_text: str, client: httpx.AsyncClient
    ) -> str:
        """Generate a topic briefing from article content."""
        prompt = (
            f"Provide a concise intelligence briefing on the topic: {topic}\n\n"
            f"Based on these recent articles:\n{articles_text}\n\n"
            "Structure the briefing as:\n"
            "1. Key developments\n"
            "2. Notable entities involved\n"
            "3. Potential implications"
        )
        return await self._complete(prompt, client, max_tokens=1000)

    async def _complete(
        self, prompt: str, client: httpx.AsyncClient, max_tokens: int = 300
    ) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0.3,
        }

        try:
            resp = await client.post(self.url, json=payload, timeout=120.0)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        except httpx.HTTPError as e:
            logger.error("LLM request failed: %s", e)
            return ""
        except (KeyError, IndexError) as e:
            logger.error("Unexpected LLM response: %s", e)
            return ""
