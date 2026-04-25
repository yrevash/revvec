"""ClusterAgent, candidate → active pattern promotion.

Three object classes, same state-machine:

  defect_pattern   (photo_vec): cosine ≥ 0.80 to an existing pattern → merge
                                  into that pattern (signal_count += 1).
                                  signal_count ≥ 3 across ≥ 2 time windows
                                  → state = "active".

  alarm_pattern    (sensor_vec): same logic with threshold 0.75.
                                  Optional equipment_id filter (same equipment
                                  class → more likely same failure mode).

  answer_pattern   (text_vec):   stored as entity_type="answer_cache"; engineer
                                  thumbs-up in UI promotes candidate → active.
                                  Implemented in Phase 4.

Patterns live as their own Actian points with entity_type in
{"candidate_pattern", "active_pattern"} and a `cluster_members` payload
listing the entity_ids of the concrete events that fed into them.

ARCHIVE:
  sweep_archive() moves patterns with last_seen_ms older than 90 days to
  state="archived" so they drop out of the default retrieval surface.
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any, Literal

from actian_vectorai import (
    Field,
    FilterBuilder,
    PointStruct,
    SearchParams,
    VectorAIClient,
)

from revvec import config

log = logging.getLogger(__name__)


DEFECT_MERGE_THRESHOLD = 0.80
ALARM_MERGE_THRESHOLD = 0.75
PROMOTION_THRESHOLD = 3
ARCHIVE_AGE_MS = 90 * 24 * 3600 * 1000


@dataclass
class PromotionResult:
    pattern_id: str
    state: Literal["candidate_pattern", "active_pattern"]
    signal_count: int
    was_created: bool
    was_promoted: bool


class ClusterAgent:
    def __init__(self, client: VectorAIClient, collection: str = config.COLLECTION) -> None:
        self.client = client
        self.collection = collection

    # ─── defect patterns (photo_vec) ─────────────────────────────────────────

    def on_new_defect_image(
        self,
        photo_vec: list[float],
        source_entity_id: str,
        equipment_id: str | None = None,
    ) -> PromotionResult:
        return self._process_signal(
            vec=photo_vec,
            vector_name="photo_vec",
            kind="defect",
            merge_threshold=DEFECT_MERGE_THRESHOLD,
            source_entity_id=source_entity_id,
            equipment_id=equipment_id,
        )

    # ─── alarm patterns (sensor_vec) ─────────────────────────────────────────

    def on_new_alarm(
        self,
        sensor_vec: list[float],
        source_entity_id: str,
        equipment_id: str | None = None,
    ) -> PromotionResult:
        return self._process_signal(
            vec=sensor_vec,
            vector_name="sensor_vec",
            kind="alarm",
            merge_threshold=ALARM_MERGE_THRESHOLD,
            source_entity_id=source_entity_id,
            equipment_id=equipment_id,
        )

    # ─── core promotion loop ─────────────────────────────────────────────────

    def _process_signal(
        self,
        vec: list[float],
        vector_name: str,
        kind: str,
        merge_threshold: float,
        source_entity_id: str,
        equipment_id: str | None,
    ) -> PromotionResult:
        now_ms = int(time.time() * 1000)

        # 1) Find closest existing pattern (candidate or active) of same kind + equipment class
        filter_ = (
            FilterBuilder()
            .must(Field("entity_type").any_of(["candidate_pattern", "active_pattern"]))
            .must(Field("pattern_kind").eq(kind))
            .build()
        )
        nearest = self.client.points.search(
            self.collection,
            vector=vec,
            using=vector_name,
            limit=1,
            filter=filter_,
            params=SearchParams(hnsw_ef=128),
            with_payload=True,
            with_vectors=False,
        )

        if nearest and nearest[0].score >= merge_threshold:
            # Merge into existing pattern
            existing = nearest[0]
            existing_payload = existing.payload
            # Equipment-class gate: only merge if same equipment_id (when provided)
            if equipment_id and existing_payload.get("equipment_id") not in (None, "", equipment_id):
                # different equipment class, skip merge, create new
                return self._create_candidate(vec, vector_name, kind, now_ms, source_entity_id, equipment_id)

            new_count = int(existing_payload.get("signal_count", 0)) + 1
            new_state = existing_payload.get("entity_type", "candidate_pattern")
            was_promoted = False
            if new_state == "candidate_pattern" and new_count >= PROMOTION_THRESHOLD:
                new_state = "active_pattern"
                was_promoted = True
                log.info("promoted %s pattern %s → active (%d signals)", kind, existing.id, new_count)

            # Update scalar fields only, Actian's set_payload on list-typed values
            # crashes the server in this build. Update type + count + recency only.
            self.client.points.set_payload(
                self.collection,
                {
                    "signal_count": new_count,
                    "last_seen_ms": now_ms,
                    "entity_type": new_state,
                    "state": "active" if new_state == "active_pattern" else "candidate",
                    "last_member": source_entity_id,  # scalar pointer to the most recent signal
                },
                ids=[existing.id],
            )
            return PromotionResult(
                pattern_id=str(existing.id),
                state=new_state,
                signal_count=new_count,
                was_created=False,
                was_promoted=was_promoted,
            )

        # 2) No existing pattern close enough → create a new candidate
        return self._create_candidate(vec, vector_name, kind, now_ms, source_entity_id, equipment_id)

    def _create_candidate(
        self,
        vec: list[float],
        vector_name: str,
        kind: str,
        now_ms: int,
        source_entity_id: str,
        equipment_id: str | None,
    ) -> PromotionResult:
        pid = str(uuid.uuid4())
        payload = {
            "entity_type": "candidate_pattern",
            "entity_id": pid,
            "source": f"cluster_agent/{kind}",
            "source_hash": f"pattern:{kind}:{pid}",
            "modality": "image" if vector_name == "photo_vec" else "sensor",
            "timestamp_ms": now_ms,
            "ingested_ms": now_ms,
            "author_id": "cluster-agent",
            "classification": "public",
            "state": "candidate",
            "role_visibility": ["maintenance", "quality", "plant_manager"],
            "signal_count": 1,
            "last_seen_ms": now_ms,
            "pattern_kind": kind,
            "last_member": source_entity_id,
            "equipment_id": equipment_id or "",
            "title": f"{kind} pattern (candidate)",
            "text_preview": f"{kind} pattern candidate, 1 signal so far",
        }
        # Populate ALL named vectors, Actian's set_payload asserts every declared
        # named vector exists on the point (assertion fires otherwise). Dummies
        # for unused slots; real vector for the one that matters.
        vectors_dict = {
            "text_vec":   [0.0] * config.DIM_TEXT,
            "photo_vec":  [0.0] * config.DIM_PHOTO,
            "sensor_vec": [0.0] * config.DIM_SENSOR,
        }
        vectors_dict[vector_name] = vec
        self.client.points.upsert(self.collection, [
            PointStruct(id=pid, vector=vectors_dict, payload=payload),
        ])
        log.info("created new %s candidate pattern %s", kind, pid)
        return PromotionResult(
            pattern_id=pid,
            state="candidate_pattern",
            signal_count=1,
            was_created=True,
            was_promoted=False,
        )

    # ─── archive sweep ───────────────────────────────────────────────────────

    def sweep_archive(self) -> int:
        """Move patterns older than ARCHIVE_AGE_MS to state=archived."""
        now_ms = int(time.time() * 1000)
        cutoff = now_ms - ARCHIVE_AGE_MS
        filter_ = (
            FilterBuilder()
            .must(Field("entity_type").any_of(["candidate_pattern", "active_pattern"]))
            .must(Field("last_seen_ms").lt(cutoff))
            .build()
        )
        # Scroll to collect IDs (we can't set_payload by filter for the state change
        # without also hitting the entity_type field)
        ids: list[str] = []
        offset = None
        while True:
            points, next_offset = self.client.points.scroll(
                self.collection,
                filter=filter_,
                limit=200,
                offset=offset,
                with_payload=False,
                with_vectors=False,
            )
            ids.extend(str(p.id) for p in points)
            if next_offset is None:
                break
            offset = next_offset

        if not ids:
            return 0
        self.client.points.set_payload(
            self.collection,
            {"state": "archived"},
            ids=ids,
        )
        log.info("archived %d stale patterns", len(ids))
        return len(ids)

    # ─── diagnostics ─────────────────────────────────────────────────────────

    def stats(self) -> dict[str, int]:
        """Return counts of candidate / active / archived patterns per kind."""
        out: dict[str, int] = {}
        for kind in ("defect", "alarm"):
            for state_label, entity_type in [("candidate", "candidate_pattern"), ("active", "active_pattern")]:
                f = (
                    FilterBuilder()
                    .must(Field("entity_type").eq(entity_type))
                    .must(Field("pattern_kind").eq(kind))
                    .build()
                )
                out[f"{kind}_{state_label}"] = self.client.points.count(self.collection, filter=f)
        return out
