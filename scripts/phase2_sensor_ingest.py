"""Phase 2 — sensor ingest from CMAPSS.

Finds the extracted CMAPSS directory under data/fetch_cache (put there by
`make fetch`), runs SensorIngestor across all four FD subdatasets, and reports
how many sensor_vec points landed in Actian.
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
from revvec.ingestion.sensor import SensorIngestor
from revvec.memory.actian_writer import MemoryAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("phase2_sensor_ingest")


def find_cmapss_dir() -> Path | None:
    """Locate the extracted CMAPSS directory under data/fetch_cache."""
    cache = config.REVVEC_DATA / "fetch_cache"
    if not cache.exists():
        return None
    # The extracted dir has a nested "6. Turbofan ..." folder that contains the .txt files
    for candidate in cache.rglob("train_FD001.txt"):
        return candidate.parent
    return None


def main() -> int:
    cmapss_dir = find_cmapss_dir()
    if cmapss_dir is None:
        log.error("CMAPSS directory not found under data/fetch_cache — run `make fetch` first")
        return 1
    log.info("using CMAPSS dir: %s", cmapss_dir)

    t0 = time.perf_counter()
    with VectorAIClient(config.ACTIAN_URL) as client:
        client.connect()
        memory = MemoryAgent(client)
        memory.ensure_ready()

        embedder = get_embedder()
        dedup = DedupStore(config.REVVEC_DATA / "dedup.sqlite")
        ingestor = SensorIngestor(memory, embedder, dedup)

        written = ingestor.ingest_cmapss_directory(cmapss_dir)
        total = memory.count()

    dt = time.perf_counter() - t0
    print(f"\n=== phase 2 sensor ingest ===")
    print(f"  new points written:  {written}")
    print(f"  total in collection: {total}")
    print(f"  wall time:           {dt:.2f}s")
    return 0 if written > 0 or total > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
