"""One-shot cleanup: delete existing sop_page points and clear :sop dedup marks.

Run before re-running phase1_sop_ingest with the updated (dual-vector) ingestor.
Keeps log + image ingest results intact.
"""
from __future__ import annotations

import logging
import sqlite3
import sys

from actian_vectorai import Field, FilterBuilder, VectorAIClient

from revvec import config
from revvec.memory.actian_writer import MemoryAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)


def main() -> int:
    with VectorAIClient(config.ACTIAN_URL) as client:
        client.connect()
        memory = MemoryAgent(client)
        memory.ensure_ready()

        before = memory.count()
        f = FilterBuilder().must(Field("entity_type").eq("sop_page")).build()
        to_delete = memory.count(filter=f)
        if to_delete:
            client.points.delete(config.COLLECTION, filter=f)
            print(f"deleted {to_delete} sop_page points")
        else:
            print("no sop_page points to delete")
        after = memory.count()
        print(f"collection size: {before} -> {after}")

    # Wipe :sop dedup marks
    dedup_path = config.REVVEC_DATA / "dedup.sqlite"
    if dedup_path.exists():
        conn = sqlite3.connect(str(dedup_path))
        cur = conn.execute("DELETE FROM fetched WHERE source_hash LIKE '%:sop'")
        conn.commit()
        print(f"cleared {cur.rowcount} :sop dedup marks")
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
