"""Actian collection schema for revvec.

One collection, four named vectors. Declared once at collection-create time and
never mutated (dynamic create_field_index is UNIMPLEMENTED server-side).

Post-April-2026 SOTA review: upgraded vector dims + models. Voice transcripts
now land in text_vec with payload modality="voice" (no separate transcript_vec).
"""
from __future__ import annotations

import logging

from actian_vectorai import (
    Distance,
    HnswConfigDiff,
    VectorAIClient,
    VectorParams,
)

from revvec import config

log = logging.getLogger(__name__)


def build_vectors_config() -> dict[str, VectorParams]:
    return {
        "text_vec":   VectorParams(size=config.DIM_TEXT,   distance=Distance.Cosine),
        "photo_vec":  VectorParams(size=config.DIM_PHOTO,  distance=Distance.Cosine),
        "sensor_vec": VectorParams(size=config.DIM_SENSOR, distance=Distance.Cosine),
    }


def ensure_collection(client: VectorAIClient, name: str = config.COLLECTION) -> bool:
    """Create the collection if it doesn't exist. Returns True iff created."""
    if client.collections.exists(name):
        log.info("Collection %s already exists", name)
        return False

    client.collections.create(
        name,
        vectors_config=build_vectors_config(),
        hnsw_config=HnswConfigDiff(m=32, ef_construct=256),
    )
    log.info("Created collection %s with 4 named vectors", name)
    return True
