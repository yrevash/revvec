"""RetrievalAgent, three-tier retrieval.

Stage 1: server-side multi-vector prefetch + RRF fusion (Actian)
Stage 2: client-side hybrid re-rank (0.7 · semantic + 0.3 · lexical)
Stage 3: answer-cache shortcut (Phase 4, deferred until LLMAgent exists)

The one public entry is `RetrievalAgent.retrieve(query_text, …)`.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from actian_vectorai import (
    Fusion,
    PrefetchQuery,
    VectorAIClient,
)

from revvec import config
from revvec.embed.service import EmbedAgent, get_embedder
from revvec.retrieval.filters import build_persona_filter
from revvec.retrieval.lexical import (
    bm25_scores,
    extract_keywords,
    passes_bm25_threshold,
    passes_hybrid_threshold,
)

log = logging.getLogger(__name__)


@dataclass
class RetrievalHit:
    id: str
    score_semantic: float
    score_lexical: float
    score_final: float
    payload: dict[str, Any] = field(default_factory=dict)

    @property
    def title(self) -> str:
        return str(self.payload.get("title", ""))

    @property
    def preview(self) -> str:
        return str(self.payload.get("text_preview", ""))


class RetrievalAgent:
    def __init__(
        self,
        client: VectorAIClient,
        collection: str = config.COLLECTION,
        embedder: EmbedAgent | None = None,
    ) -> None:
        self.client = client
        self.collection = collection
        self.embedder = embedder or get_embedder()

    # ─── main entry ──────────────────────────────────────────────────────────

    def retrieve(
        self,
        query_text: str = "",
        *,
        persona: str | None = None,
        time_range_ms: tuple[int, int] | None = None,
        equipment_id: str | None = None,
        image_query: Any = None,          # PIL.Image.Image, import deferred
        sensor_window: np.ndarray | None = None,
        limit: int = 6,
        prefetch_limit_text: int = 40,
        prefetch_limit_photo: int = 20,
        prefetch_limit_sensor: int = 20,
        filter_override: Any = None,
    ) -> list[RetrievalHit]:
        """One-shot retrieval across all populated named vectors + re-rank."""
        t0 = time.perf_counter()

        from revvec.retrieval.filters import DEFAULT_CONTENT_ENTITY_TYPES

        # NOTE on Actian filter behaviour in this build: after heavy upsert/
        # delete churn (Phases 2–5), server-side search(..., filter=...) starts
        # returning 0 hits across all values of entity_type / state, even
        # though count(..., filter=...) returns correct numbers. Root cause
        # looks like stale payload-index state after server restarts (the
        # dynamic create_field_index RPC that would fix this is UNIMPLEMENTED
        # in v1.0). Workaround: do server-side search WITHOUT filter, then
        # post-filter client-side. Slower per-query but functionally correct.

        # Embed whichever inputs are provided
        query_text_vec = (
            self.embedder.embed_text(query_text)[0].tolist() if query_text else None
        )
        query_photo_vec = (
            self.embedder.embed_photo(image_query)[0].tolist() if image_query is not None else None
        )
        query_sensor_vec = (
            self.embedder.embed_sensor(sensor_window)[0].tolist()
            if sensor_window is not None
            else None
        )

        # Build prefetches with NO filter (client-side filter applied later)
        prefetch: list[PrefetchQuery] = []
        if query_text_vec is not None:
            prefetch.append(PrefetchQuery(using="text_vec", query=query_text_vec, limit=prefetch_limit_text * 2))
        if query_photo_vec is not None:
            prefetch.append(PrefetchQuery(using="photo_vec", query=query_photo_vec, limit=prefetch_limit_photo * 2))
        if query_sensor_vec is not None:
            prefetch.append(PrefetchQuery(using="sensor_vec", query=query_sensor_vec, limit=prefetch_limit_sensor * 2))

        if not prefetch:
            return []

        # Stage 1: Actian, either direct search (1 prefetch) or RRF fusion (2+)
        # Big over-fetch (200+) so post-filter has material to work with.
        t_stage1 = time.perf_counter()
        over_fetch = max(200, limit * 40)
        if len(prefetch) == 1:
            pf = prefetch[0]
            hits = self.client.points.search(
                self.collection,
                vector=pf.query,
                using=pf.using,
                limit=over_fetch,
                with_payload=True,
                score_threshold=-1.0,
            )
        else:
            hits = self.client.points.query(
                self.collection,
                prefetch=prefetch,
                query={"fusion": Fusion.RRF},
                limit=over_fetch,
                with_payload=True,
            )

        # Client-side filter: state="active", entity_type in allowed set
        allowed_types = set(DEFAULT_CONTENT_ENTITY_TYPES)
        filtered = []
        for h in hits:
            p = h.payload or {}
            if p.get("state") and p.get("state") != "active":
                continue
            if p.get("entity_type") not in allowed_types:
                continue
            if equipment_id and p.get("equipment_id") and p.get("equipment_id") != equipment_id:
                continue
            filtered.append(h)
        hits = filtered[: max(20, limit * 4)]  # trim back to a manageable rerank set
        t_stage1_ms = (time.perf_counter() - t_stage1) * 1000
        log.info("stage-1 RRF returned %d hits in %.0f ms", len(hits), t_stage1_ms)

        # Stage 2: hybrid re-rank with real Okapi BM25 over the candidate
        # pool (industrial-code-aware tokenizer keeps SOP-ME-112 etc intact).
        t_stage2 = time.perf_counter()
        ranked: list[RetrievalHit] = []
        if query_text and hits:
            doc_blobs = [
                f"{h.payload.get('title', '')} {h.payload.get('text_preview', '')}"
                for h in hits
            ]
            bm25_norm = bm25_scores(query_text, doc_blobs)
        else:
            bm25_norm = [0.0] * len(hits)
        for h, bm25 in zip(hits, bm25_norm):
            passes, final = passes_bm25_threshold(float(h.score), bm25)
            if not passes:
                continue
            ranked.append(RetrievalHit(
                id=str(h.id),
                score_semantic=float(h.score),
                score_lexical=bm25,  # BM25 normalised to [0, 1]
                score_final=final,
                payload=h.payload,
            ))

        # If everything filtered out, fall back to ranking Stage-1 hits by
        # their raw semantic score, better than returning nothing.
        if not ranked:
            log.info("hybrid re-rank dropped all hits; falling back to pure-semantic top-k")
            for h in hits[:limit]:
                ranked.append(RetrievalHit(
                    id=str(h.id),
                    score_semantic=float(h.score),
                    score_lexical=0.0,
                    score_final=float(h.score),  # use raw semantic
                    payload=h.payload,
                ))
        else:
            ranked.sort(key=lambda x: -x.score_final)
            ranked = ranked[:limit]

        total_ms = (time.perf_counter() - t0) * 1000
        t_stage2_ms = (time.perf_counter() - t_stage2) * 1000
        log.info(
            "retrieve: %d hits (stage1=%.0fms stage2=%.0fms total=%.0fms)",
            len(ranked), t_stage1_ms, t_stage2_ms, total_ms,
        )
        return ranked
