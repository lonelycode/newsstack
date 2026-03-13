from __future__ import annotations

import asyncio
import logging
import uuid

import hdbscan
import numpy as np

from newsstack.db.models import Cluster
from newsstack.db.queries import (
    get_unclustered_article_ids,
    update_article_cluster,
    upsert_cluster,
    get_articles_by_ids,
)
from newsstack.vectors.qdrant import VectorStore

logger = logging.getLogger(__name__)


async def run_clustering(
    db,
    vector_store: VectorStore,
    summarizer,
    http_client,
    min_cluster_size: int = 3,
) -> int:
    """Cluster unclustered articles. Returns number of clusters created."""
    article_ids = await get_unclustered_article_ids(db, hours=24)
    if len(article_ids) < min_cluster_size:
        logger.debug("Not enough unclustered articles (%d) to cluster", len(article_ids))
        return 0

    # Get vectors from Qdrant
    vectors_map = await vector_store.get_vectors(article_ids)
    if len(vectors_map) < min_cluster_size:
        return 0

    # Align IDs and vectors
    ids = list(vectors_map.keys())
    vectors = np.array([vectors_map[aid] for aid in ids])

    # Run HDBSCAN in a thread
    def _cluster():
        clusterer = hdbscan.HDBSCAN(
            min_cluster_size=min_cluster_size,
            metric="euclidean",
            cluster_selection_method="eom",
        )
        return clusterer.fit_predict(vectors)

    labels = await asyncio.to_thread(_cluster)

    # Group articles by cluster label (ignore noise = -1)
    cluster_groups: dict[int, list[str]] = {}
    for aid, label in zip(ids, labels):
        if label >= 0:
            cluster_groups.setdefault(label, []).append(aid)

    clusters_created = 0
    for _, group_ids in cluster_groups.items():
        cluster_id = str(uuid.uuid4())

        # Update article cluster_id in SQLite
        for aid in group_ids:
            await update_article_cluster(db, aid, cluster_id)

        # Get articles for summary
        articles = await get_articles_by_ids(db, group_ids)
        titles = [a.title for a in articles]

        # Generate cluster label and summary
        label_text = titles[0] if titles else "Unknown topic"
        summary = ""
        if summarizer and titles:
            summary = await summarizer.summarize_cluster(titles, http_client)

        cluster = Cluster(
            id=cluster_id,
            label=label_text[:200],
            summary=summary,
            article_count=len(group_ids),
        )
        await upsert_cluster(db, cluster)
        clusters_created += 1

    if clusters_created:
        await db.commit()
        logger.info("Created %d clusters from %d articles", clusters_created, len(ids))

    return clusters_created
