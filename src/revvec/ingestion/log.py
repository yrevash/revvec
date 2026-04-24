"""LogIngestor — ingests structured JSON / JSONL / CSV rows into text_vec.

First real customer: the fetcher's `data/fetch_log.jsonl`, which records every
NTRS PDF and Image Library asset we downloaded. For each entry we create ONE
text_vec point whose `text_preview` is the title (plus any available abstract
or caption). This lights up Phase-1 end-to-end with real data before the
SopIngestor (PDF-page embedding) or ImageIngestor (DINOv3) are online.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any

from actian_vectorai import PointStruct

from revvec import config
from revvec.embed.service import EmbedAgent, get_embedder
from revvec.ingestion.dedup import DedupStore
from revvec.memory.actian_writer import MemoryAgent

log = logging.getLogger(__name__)


_ENTITY_TYPE_BY_SOURCE = {
    "ntrs": "ntrs_document",
    "nasa_images": "nasa_image_caption",
    "direct_pdf": "ntrs_document",      # user-uploaded PDFs are logically the same
    "direct_image": "nasa_image_caption",
    "local_dir": "incident_report",     # local structured docs are treated as reports
}


class LogIngestor:
    def __init__(
        self,
        memory: MemoryAgent,
        embedder: EmbedAgent | None = None,
        dedup: DedupStore | None = None,
    ) -> None:
        self.memory = memory
        self.embedder = embedder or get_embedder()
        self.dedup = dedup or DedupStore(config.REVVEC_DATA / "dedup.sqlite")

    # ─── core ────────────────────────────────────────────────────────────────

    def ingest_fetch_log(self, log_path: Path) -> int:
        """Read a fetch_log.jsonl and ingest one text_vec entry per asset."""
        if not log_path.exists():
            log.warning("fetch log does not exist: %s", log_path)
            return 0

        entries: list[dict[str, Any]] = []
        with log_path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    log.warning("malformed fetch log line, skipping: %.80s", line)

        if not entries:
            return 0

        # Dedup within file first (we may have re-appended the same asset)
        seen_in_file: set[str] = set()
        deduped_file: list[dict[str, Any]] = []
        for e in entries:
            h = e.get("sha256")
            if not h or h in seen_in_file:
                continue
            seen_in_file.add(h)
            deduped_file.append(e)

        # Dedup against persistent store
        candidates = [
            (e["sha256"], _ENTITY_TYPE_BY_SOURCE.get(e.get("source_type", ""), "ntrs_document"))
            for e in deduped_file
        ]
        fresh_pairs = dict(self.dedup.filter_new(candidates))
        fresh_entries = [e for e in deduped_file if e.get("sha256") in fresh_pairs]

        if not fresh_entries:
            log.info("log_ingest: 0 fresh entries (all %d already ingested)", len(deduped_file))
            return 0

        log.info("log_ingest: %d fresh entries to embed (of %d unique in file)",
                 len(fresh_entries), len(deduped_file))

        # Embed all titles in one batch
        texts = [self._make_text(e) for e in fresh_entries]
        vecs = self.embedder.embed_text(texts)

        # Build points
        now_ms = int(time.time() * 1000)
        points: list[PointStruct] = []
        for e, vec in zip(fresh_entries, vecs):
            entity_type = _ENTITY_TYPE_BY_SOURCE.get(e.get("source_type", ""), "ntrs_document")
            title = e.get("title", "") or e.get("nasa_id", "") or "(untitled)"
            payload = {
                "entity_type": entity_type,
                "entity_id": str(uuid.uuid4()),
                "source": e.get("url", ""),
                "source_hash": e["sha256"],
                "modality": "text",
                "timestamp_ms": int(e.get("ts", time.time()) * 1000) if isinstance(e.get("ts"), (int, float)) else now_ms,
                "ingested_ms": now_ms,
                "author_id": "nasa-public",
                "classification": "public",
                "state": "active",
                "role_visibility": ["new_hire", "maintenance", "quality", "plant_manager"],
                "text_preview": (title or "")[:512],
                "title": title,
                "query": e.get("query", ""),
                "nasa_id": e.get("nasa_id", ""),
                "media_sha256": e["sha256"],
            }
            points.append(PointStruct(
                id=payload["entity_id"],
                vector={"text_vec": vec.tolist()},
                payload=payload,
            ))

        written = self.memory.upsert(points)
        # Mark only after successful write
        for e in fresh_entries:
            self.dedup.mark(
                e["sha256"],
                _ENTITY_TYPE_BY_SOURCE.get(e.get("source_type", ""), "ntrs_document"),
            )
        log.info("log_ingest: wrote %d text_vec points", written)
        return written

    # ─── helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    def _make_text(e: dict[str, Any]) -> str:
        """Compose the text to embed from a fetch_log entry.

        For now: just the title. When the fetcher captures abstracts we append
        them here (Phase 1.5 enhancement).
        """
        title = e.get("title", "").strip()
        query = e.get("query", "").strip()
        if title and query:
            return f"{title} — search query: {query}"
        if title:
            return title
        return e.get("nasa_id", "") or e.get("url", "")
