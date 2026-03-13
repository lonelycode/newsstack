from __future__ import annotations

import asyncio
import logging

from newsstack.db.models import Entity

logger = logging.getLogger(__name__)

NER_LABELS = [
    "person",
    "organization",
    "location",
    "country",
    "political party",
    "event",
]


class NERProcessor:
    def __init__(self) -> None:
        self.model = None

    async def load(self) -> None:
        """Load GLiNER model in a thread to avoid blocking."""
        from gliner import GLiNER

        def _load():
            return GLiNER.from_pretrained("urchade/gliner_medium-v2.1")

        logger.info("Loading GLiNER model...")
        self.model = await asyncio.to_thread(_load)
        logger.info("GLiNER model loaded")

    async def extract(self, article_id: str, text: str) -> list[Entity]:
        """Extract named entities from text."""
        if self.model is None:
            return []

        # Truncate to avoid excessive processing
        text = text[:2000]

        def _predict():
            return self.model.predict_entities(text, NER_LABELS, threshold=0.4)

        raw_entities = await asyncio.to_thread(_predict)

        entities: list[Entity] = []
        seen: set[tuple[str, str]] = set()
        for ent in raw_entities:
            key = (ent["text"].lower(), ent["label"])
            if key not in seen:
                seen.add(key)
                entities.append(
                    Entity(
                        article_id=article_id,
                        text=ent["text"],
                        label=ent["label"],
                    )
                )

        return entities
