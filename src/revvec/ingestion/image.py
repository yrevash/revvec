"""ImageIngestor, JPG/PNG → DINOv3 ViT-L → photo_vec (1024d).

Consumes `data/fetch_log.jsonl` entries where source_type in {nasa_images,
direct_image, local_dir-image}. Reads each cached image, embeds via the
EmbedAgent's DINOv3 path, and upserts a photo_vec point per image.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from PIL import Image
from actian_vectorai import PointStruct

from revvec import config
from revvec.embed.service import EmbedAgent, get_embedder
from revvec.ingestion.dedup import DedupStore
from revvec.memory.actian_writer import MemoryAgent

log = logging.getLogger(__name__)


CACHE_DIR = config.REVVEC_DATA / "fetch_cache"


def _url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def _cached_path(url: str) -> Path | None:
    """Resolve the cache file for a URL, trying .jpg / .jpeg / .png in order."""
    h = _url_hash(url)
    # Prefer the extension found in the URL itself
    ext = os.path.splitext(urlparse(url).path)[1].lower()
    tried = []
    for e in [ext, ".jpg", ".jpeg", ".png"]:
        if not e:
            continue
        p = CACHE_DIR / f"{h}{e}"
        tried.append(p)
        if p.exists():
            return p
    return None


class ImageIngestor:
    def __init__(
        self,
        memory: MemoryAgent,
        embedder: EmbedAgent | None = None,
        dedup: DedupStore | None = None,
        batch_size: int = 8,
    ) -> None:
        self.memory = memory
        self.embedder = embedder or get_embedder()
        self.dedup = dedup or DedupStore(config.REVVEC_DATA / "dedup.sqlite")
        self.batch_size = batch_size

    def ingest_fetch_log(self, log_path: Path) -> int:
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
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if d.get("source_type") in {"nasa_images", "direct_image"}:
                    entries.append(d)

        if not entries:
            log.info("image_ingest: no image entries in fetch log")
            return 0

        # File-level dedup (multiple log entries for same sha256)
        seen_in_file: set[str] = set()
        deduped: list[dict[str, Any]] = []
        for e in entries:
            h = e.get("sha256")
            if not h or h in seen_in_file:
                continue
            seen_in_file.add(h)
            deduped.append(e)

        # Persistent dedup, different namespace than LogIngestor's text_vec
        # for the same sha256: mark as entity_type=equipment_photo so we can
        # re-ingest the same asset for the photo_vec path without collision.
        candidates = [(e["sha256"] + ":photo", "equipment_photo") for e in deduped]
        fresh_pairs = dict(self.dedup.filter_new(candidates))
        fresh = [e for e in deduped if (e["sha256"] + ":photo") in fresh_pairs]

        if not fresh:
            log.info("image_ingest: 0 fresh images (all %d already ingested)", len(deduped))
            return 0

        log.info("image_ingest: %d fresh images to embed", len(fresh))

        written = 0
        # Batch through the embedder
        for batch_start in range(0, len(fresh), self.batch_size):
            batch = fresh[batch_start : batch_start + self.batch_size]
            images: list[Image.Image] = []
            good_entries: list[dict[str, Any]] = []
            for e in batch:
                p = _cached_path(e.get("url", ""))
                if p is None:
                    log.warning("image_ingest: cache miss for %s", e.get("url", "")[:80])
                    continue
                try:
                    img = Image.open(p)
                    img.load()
                    images.append(img)
                    good_entries.append(e)
                except Exception as ex:  # noqa: BLE001
                    log.warning("image_ingest: failed to open %s: %r", p, ex)

            if not images:
                continue

            vecs = self.embedder.embed_photo(images)

            now_ms = int(time.time() * 1000)
            points: list[PointStruct] = []
            for e, vec in zip(good_entries, vecs):
                title = e.get("title", "") or e.get("nasa_id", "") or "(untitled)"
                payload = {
                    "entity_type": "equipment_photo",
                    "entity_id": str(uuid.uuid4()),
                    "source": e.get("url", ""),
                    "source_hash": e["sha256"] + ":photo",
                    "modality": "image",
                    "timestamp_ms": int(e.get("ts", time.time()) * 1000) if isinstance(e.get("ts"), (int, float)) else now_ms,
                    "ingested_ms": now_ms,
                    "author_id": "nasa-public",
                    "classification": "public",
                    "state": "active",
                    "role_visibility": ["maintenance", "quality", "plant_manager"],
                    "text_preview": title[:512],
                    "title": title,
                    "query": e.get("query", ""),
                    "nasa_id": e.get("nasa_id", ""),
                    "media_sha256": e["sha256"],
                }
                points.append(PointStruct(
                    id=payload["entity_id"],
                    vector={"photo_vec": vec.tolist()},
                    payload=payload,
                ))

            written += self.memory.upsert(points)
            for e in good_entries:
                self.dedup.mark(e["sha256"] + ":photo", "equipment_photo")

        log.info("image_ingest: wrote %d photo_vec points", written)
        return written
