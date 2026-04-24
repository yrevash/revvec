"""MemoryAgent — the single writer into Actian.

Every ingestor funnels through this. It enforces the payload schema (no
undeclared fields leak in), batches writes, and retries on transient gRPC
`UNAVAILABLE`. This is where daily VDE snapshots are triggered (Phase 7).

The payload schema is declared in one place (see PAYLOAD_REQUIRED + PAYLOAD_OPTIONAL
below) to prevent drift across ingestors.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Iterable, Iterator, Sequence
from typing import Any

from actian_vectorai import (
    PointStruct,
    VectorAIClient,
)

from revvec import config
from revvec.memory.schema import ensure_collection

log = logging.getLogger(__name__)


# Payload fields — declared in one place, referenced from every ingestor.
PAYLOAD_REQUIRED: frozenset[str] = frozenset({
    "entity_type",
    "entity_id",
    "source",
    "source_hash",
    "modality",
    "timestamp_ms",
    "ingested_ms",
    "author_id",
    "classification",
    "state",
})

PAYLOAD_OPTIONAL: frozenset[str] = frozenset({
    "parent_id",
    "role_visibility",
    "line_id",
    "equipment_id",
    "shift",
    "severity",
    "signal_count",
    "last_seen_ms",
    "media_sha256",
    "text_preview",
    "audit_prev_hash",
    "audit_row_hash",
    "query",          # for fetch-originating entries — what search produced them
    "nasa_id",        # for Image Library entries
    "title",
    # ClusterAgent pattern bookkeeping (Phase 2)
    "pattern_kind",
    "last_member",   # scalar pointer to the most recent signal's entity_id
    # Answer cache (Phase 4)
    "persona_key",
    "question",
    "answer_text",
    "citations_json",
})

_ALL_PAYLOAD_KEYS: frozenset[str] = PAYLOAD_REQUIRED | PAYLOAD_OPTIONAL


ENTITY_TYPES: frozenset[str] = frozenset({
    "sop_page", "equipment_photo", "defect_photo", "sensor_window",
    "alarm_incident", "incident_report", "shift_note", "training_clip",
    "voice_note", "answer_cache",
    "candidate_pattern",  # Phase 2 — ClusterAgent, not yet promoted
    "active_pattern",     # Phase 2 — ClusterAgent, ≥3 signals confirmed
    "archived_pattern",   # Phase 2 — state transition after 90-day dormancy
    "ntrs_document",      # Phase 1 — NTRS paper metadata ingested as text_vec
    "nasa_image_caption", # Phase 1 — Image Library caption as text_vec
})

MODALITIES: frozenset[str] = frozenset({"text", "image", "sensor", "voice", "structured"})


def _batched(items: Sequence[Any], size: int) -> Iterator[Sequence[Any]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


class PayloadValidationError(ValueError):
    pass


class MemoryAgent:
    """Thin wrapper around the Actian client enforcing schema + batching + retry."""

    def __init__(
        self,
        client: VectorAIClient,
        *,
        collection: str = config.COLLECTION,
        batch_size: int = 64,
        max_retries: int = 3,
    ) -> None:
        self.client = client
        self.collection = collection
        self.batch_size = batch_size
        self.max_retries = max_retries

    # ─── setup ───────────────────────────────────────────────────────────────

    def ensure_ready(self) -> bool:
        """Idempotently create the collection if missing, and always open it.

        After an Actian server restart the collection files persist on disk but
        the in-memory handle is closed — `collections.exists()` lies (returns
        False) and `points.count()` raises CollectionNotFoundError. Explicit
        `vde.open_collection()` is required to remount the collection state.
        """
        created = False
        try:
            created = ensure_collection(self.client, self.collection)
        except Exception as e:  # noqa: BLE001
            log.warning("ensure_collection raised %r; attempting vde.open_collection", e)
        # Always try to open — cheap and idempotent
        try:
            self.client.vde.open_collection(self.collection)
        except Exception as e:  # noqa: BLE001
            log.warning("vde.open_collection failed: %r", e)
        return created

    # ─── validation ──────────────────────────────────────────────────────────

    def _validate_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        missing = PAYLOAD_REQUIRED - set(payload.keys())
        if missing:
            raise PayloadValidationError(f"missing required fields: {sorted(missing)}")
        et = payload["entity_type"]
        if et not in ENTITY_TYPES:
            raise PayloadValidationError(f"unknown entity_type: {et}")
        mod = payload["modality"]
        if mod not in MODALITIES:
            raise PayloadValidationError(f"unknown modality: {mod}")
        unknown = set(payload.keys()) - _ALL_PAYLOAD_KEYS
        if unknown:
            # Not fatal — we drop unknown keys silently to stop bad ingestors
            # from bloating the payload schema. Logged once per call.
            log.warning("dropping unknown payload keys: %s", sorted(unknown))
            payload = {k: v for k, v in payload.items() if k in _ALL_PAYLOAD_KEYS}
        return payload

    # ─── upsert ──────────────────────────────────────────────────────────────

    def upsert(self, points: Sequence[PointStruct]) -> int:
        """Upsert a batch of validated points. Returns the count written."""
        # Validate in one pass — fail fast before we hit Actian.
        clean: list[PointStruct] = []
        for p in points:
            p.payload = self._validate_payload(p.payload)
            clean.append(p)

        written = 0
        for chunk in _batched(clean, self.batch_size):
            for attempt in range(self.max_retries + 1):
                try:
                    self.client.points.upsert(self.collection, list(chunk))
                    written += len(chunk)
                    break
                except Exception as e:  # noqa: BLE001
                    if attempt == self.max_retries:
                        log.error("upsert failed after %d attempts: %r", self.max_retries, e)
                        raise
                    backoff = 0.2 * (2 ** attempt)
                    log.warning("upsert attempt %d failed (%r); retrying in %.1fs", attempt, e, backoff)
                    time.sleep(backoff)
        return written

    # ─── read helpers ────────────────────────────────────────────────────────

    def count(self, *, filter: Any = None) -> int:
        return self.client.points.count(self.collection, filter=filter)

    def delete_by_ids(self, ids: Iterable[str | int]) -> None:
        self.client.points.delete(self.collection, ids=list(ids), strict=False)

    def snapshot(self) -> bool:
        """VDE snapshot for daily audit immutability (Phase 7)."""
        return self.client.vde.save_snapshot(self.collection)
