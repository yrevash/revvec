"""Answer cache — repeat queries served without re-running the LLM.

Writes every generated answer back into Actian as `entity_type=answer_cache`
with the question's text_vec as the key. A new query with cosine ≥ 0.95 to a
cached entry of the same persona returns the cached answer instantly (target:
< 150 ms end-to-end).

Candidate → active state transitions follow the ClusterAgent pattern: a fresh
answer is `state="candidate"`. Engineer thumbs-up in the UI (Phase 6) promotes
to `state="active"`, raising its retrieval priority.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import asdict
from typing import Any

from actian_vectorai import (
    Field,
    FilterBuilder,
    PointStruct,
    VectorAIClient,
)

from revvec import config

log = logging.getLogger(__name__)


CACHE_HIT_THRESHOLD = 0.95


class AnswerCache:
    def __init__(self, client: VectorAIClient, collection: str = config.COLLECTION) -> None:
        self.client = client
        self.collection = collection

    # ─── lookup ──────────────────────────────────────────────────────────────

    def lookup(self, query_embedding: list[float], persona: str) -> dict[str, Any] | None:
        """Return the cached answer dict if a match ≥ threshold exists."""
        f = (
            FilterBuilder()
            .must(Field("entity_type").eq("answer_cache"))
            .must(Field("persona_key").eq(persona))
            .build()
        )
        hits = self.client.points.search(
            self.collection,
            vector=query_embedding,
            using="text_vec",
            limit=1,
            filter=f,
            score_threshold=CACHE_HIT_THRESHOLD,
            with_payload=True,
        )
        if not hits:
            return None
        h = hits[0]
        log.info("answer_cache HIT score=%.3f persona=%s", h.score, persona)
        payload = h.payload
        return {
            "answer": payload.get("answer_text", ""),
            "citations_json": payload.get("citations_json", "[]"),
            "question": payload.get("question", ""),
            "persona": payload.get("persona_key", persona),
            "cache_hit_score": float(h.score),
        }

    # ─── write-back ──────────────────────────────────────────────────────────

    def write(
        self,
        query_embedding: list[float],
        persona: str,
        question: str,
        answer: str,
        citations: list[Any],
    ) -> str:
        """Store a fresh answer as entity_type=answer_cache (state=candidate).

        All three named vectors are populated — text_vec with the real query
        embedding, photo_vec and sensor_vec with zeros — because Actian's
        set_payload (used for future thumbs-up promotion) crashes when any
        declared named vector is missing on a point.
        """
        pid = str(uuid.uuid4())
        now_ms = int(time.time() * 1000)
        citations_serializable = [
            {"index": c.index, "entity_id": c.entity_id, "title": c.title}
            for c in citations
        ]
        payload = {
            "entity_type": "answer_cache",
            "entity_id": pid,
            "source": "llm_agent",
            "source_hash": f"answer:{pid}",
            "modality": "text",
            "timestamp_ms": now_ms,
            "ingested_ms": now_ms,
            "author_id": "revvec-llm",
            "classification": "public",
            "state": "candidate",
            "role_visibility": ["new_hire", "maintenance", "quality", "plant_manager"],
            "persona_key": persona,
            "question": question[:1000],
            "answer_text": answer[:4000],
            "citations_json": json.dumps(citations_serializable),
            "title": f"answer for: {question[:80]}",
            "text_preview": answer[:512],
            "signal_count": 1,
            "last_seen_ms": now_ms,
            "pattern_kind": "answer",
        }
        vectors = {
            "text_vec":   query_embedding,
            "photo_vec":  [0.0] * config.DIM_PHOTO,
            "sensor_vec": [0.0] * config.DIM_SENSOR,
        }
        self.client.points.upsert(self.collection, [
            PointStruct(id=pid, vector=vectors, payload=payload),
        ])
        log.info("answer_cache WRITE pid=%s persona=%s", pid, persona)
        return pid
