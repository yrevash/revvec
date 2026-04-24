"""SopIngestor — PDF → ColPali-style page-as-image + extracted text.

Each PDF page becomes ONE Actian point (entity_type=sop_page) with BOTH named
vectors populated:
  - text_vec : Qwen3-Embedding over the page's extracted text
  - photo_vec: DINOv2 ViT-L over the page rendered as an image (150 DPI)

Why both: ColPali's key insight is that a document page is fundamentally visual
— figures, diagrams, tables, equations, and layout carry meaning that plain
text extraction throws away. DINOv2 on the rendered page captures all of that
visual information as a single 1024d vector. Pairing it with text_vec lets
retrieval fuse both signals via Actian server-side RRF.

Actian doesn't support late-interaction scoring so we can't use ColPali's
per-token matching directly; instead we get a near-equivalent by giving each
page two independent dense vectors and letting RRF do the fusion at query time.
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

import pymupdf
from PIL import Image
from actian_vectorai import PointStruct

from revvec import config
from revvec.embed.service import EmbedAgent, get_embedder
from revvec.ingestion.dedup import DedupStore
from revvec.memory.actian_writer import MemoryAgent

log = logging.getLogger(__name__)


CACHE_DIR = config.REVVEC_DATA / "fetch_cache"
PAGE_RENDER_DPI = 150
MIN_PAGE_TEXT_CHARS = 40
MAX_PAGE_TEXT_CHARS = 4000


def _url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def _pdf_cache_path(url: str) -> Path | None:
    h = _url_hash(url)
    ext = os.path.splitext(urlparse(url).path)[1].lower() or ".pdf"
    p = CACHE_DIR / f"{h}{ext}"
    return p if p.exists() else None


class SopIngestor:
    def __init__(
        self,
        memory: MemoryAgent,
        embedder: EmbedAgent | None = None,
        dedup: DedupStore | None = None,
        max_pages_per_pdf: int = 80,
        page_batch: int = 4,   # smaller batch — DINOv2 needs more memory than pure text
    ) -> None:
        self.memory = memory
        self.embedder = embedder or get_embedder()
        self.dedup = dedup or DedupStore(config.REVVEC_DATA / "dedup.sqlite")
        self.max_pages_per_pdf = max_pages_per_pdf
        self.page_batch = page_batch

    def ingest_fetch_log(self, log_path: Path) -> int:
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
                if d.get("source_type") in {"ntrs", "direct_pdf"}:
                    entries.append(d)

        seen: set[str] = set()
        deduped: list[dict[str, Any]] = []
        for e in entries:
            h = e.get("sha256")
            if not h or h in seen:
                continue
            seen.add(h)
            deduped.append(e)

        candidates = [(e["sha256"] + ":sop", "sop_page") for e in deduped]
        fresh_pairs = dict(self.dedup.filter_new(candidates))
        fresh = [e for e in deduped if (e["sha256"] + ":sop") in fresh_pairs]

        if not fresh:
            log.info("sop_ingest: 0 fresh PDFs (all %d already ingested)", len(deduped))
            return 0

        log.info("sop_ingest: processing %d fresh PDFs (page-as-image + text)", len(fresh))
        total_written = 0
        for e in fresh:
            pdf_path = _pdf_cache_path(e.get("url", ""))
            if pdf_path is None:
                log.warning("sop_ingest: cache miss for %s", e.get("url", "")[:80])
                continue
            try:
                total_written += self._ingest_one_pdf(e, pdf_path)
                self.dedup.mark(e["sha256"] + ":sop", "sop_page")
            except Exception as ex:  # noqa: BLE001
                log.warning("sop_ingest: failed on %s: %r", pdf_path.name, ex)

        log.info("sop_ingest: wrote %d sop_page points (dual-vector) from %d PDFs",
                 total_written, len(fresh))
        return total_written

    # ─── per-PDF ─────────────────────────────────────────────────────────────

    def _ingest_one_pdf(self, entry: dict[str, Any], pdf_path: Path) -> int:
        doc = pymupdf.open(str(pdf_path))
        n_pages = min(doc.page_count, self.max_pages_per_pdf)
        parent_id = str(uuid.uuid4())

        # Collect pages (render + extract text in one pass to keep the file handle open)
        pages: list[tuple[int, str, Image.Image]] = []
        for page_idx in range(n_pages):
            page = doc[page_idx]
            text = page.get_text().strip()
            if len(text) < MIN_PAGE_TEXT_CHARS:
                continue
            if len(text) > MAX_PAGE_TEXT_CHARS:
                text = text[:MAX_PAGE_TEXT_CHARS]
            pix = page.get_pixmap(dpi=PAGE_RENDER_DPI)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            pages.append((page_idx + 1, text, img))
        doc.close()

        if not pages:
            log.info("sop_ingest: %s has no usable text pages", pdf_path.name)
            return 0

        title = entry.get("title", "") or pdf_path.stem
        now_ms = int(time.time() * 1000)
        ts_ms = int(entry.get("ts", time.time()) * 1000) if isinstance(entry.get("ts"), (int, float)) else now_ms

        written = 0
        for batch_start in range(0, len(pages), self.page_batch):
            batch = pages[batch_start : batch_start + self.page_batch]
            texts = [t for _, t, _ in batch]
            images = [img for _, _, img in batch]

            # Dual-embed: text + whole-page visual
            text_vecs = self.embedder.embed_text(texts)
            photo_vecs = self.embedder.embed_photo(images)

            points: list[PointStruct] = []
            for (page_num, text, _), tv, pv in zip(batch, text_vecs, photo_vecs):
                payload = {
                    "entity_type": "sop_page",
                    "entity_id": str(uuid.uuid4()),
                    "parent_id": parent_id,
                    "source": entry.get("url", str(pdf_path)),
                    "source_hash": entry["sha256"] + f":page_{page_num}",
                    "modality": "image",  # page-as-image primary; text is a co-signal
                    "timestamp_ms": ts_ms,
                    "ingested_ms": now_ms,
                    "author_id": "nasa-public",
                    "classification": "public",
                    "state": "active",
                    "role_visibility": ["new_hire", "maintenance", "quality", "plant_manager"],
                    "text_preview": text[:512],
                    "title": f"{title} — page {page_num}",
                    "query": entry.get("query", ""),
                    "media_sha256": entry["sha256"],
                }
                points.append(PointStruct(
                    id=payload["entity_id"],
                    vector={
                        "text_vec":  tv.tolist(),
                        "photo_vec": pv.tolist(),
                    },
                    payload=payload,
                ))
            written += self.memory.upsert(points)

        return written
