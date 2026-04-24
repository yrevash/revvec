"""Phase 1 — SOP ingest.

Reads data/fetch_log.jsonl, opens each cached NTRS PDF, renders each page at
150 DPI, embeds via Nomic Embed Multimodal 3B, and upserts one page_vec point
per page.
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

from actian_vectorai import VectorAIClient

from revvec import config
from revvec.embed.service import get_embedder
from revvec.ingestion.dedup import DedupStore
from revvec.ingestion.sop import SopIngestor
from revvec.memory.actian_writer import MemoryAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

FETCH_LOG = Path(__file__).resolve().parent.parent / "data" / "fetch_log.jsonl"


def main() -> int:
    t0 = time.perf_counter()
    with VectorAIClient(config.ACTIAN_URL) as client:
        client.connect()
        memory = MemoryAgent(client)
        memory.ensure_ready()

        embedder = get_embedder()
        dedup = DedupStore(config.REVVEC_DATA / "dedup.sqlite")
        ingestor = SopIngestor(memory, embedder, dedup)

        written = ingestor.ingest_fetch_log(FETCH_LOG)
        total = memory.count()

    dt = time.perf_counter() - t0
    print(f"\n=== phase 1 SOP ingest ===")
    print(f"  new points written:  {written}")
    print(f"  total in collection: {total}")
    print(f"  wall time:           {dt:.2f}s")
    return 0 if written > 0 or total > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
