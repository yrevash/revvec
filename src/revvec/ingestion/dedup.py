"""Content-hash dedup side-car.

A tiny SQLite table: (source_hash TEXT PRIMARY KEY, entity_type TEXT, first_seen INT).
Every ingestor consults it before embedding; seen hashes are skipped.

Why SQLite here instead of an Actian query? Because (a) we want to decide
whether to embed BEFORE paying the embedding cost, (b) Actian queries require
the point to already be there, and (c) the dedup table is ops-local, not
retrieval-relevant.
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS fetched (
    source_hash TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    first_seen INTEGER NOT NULL
);
"""


class DedupStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path))
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def seen(self, source_hash: str) -> bool:
        cur = self._conn.execute(
            "SELECT 1 FROM fetched WHERE source_hash = ? LIMIT 1",
            (source_hash,),
        )
        return cur.fetchone() is not None

    def mark(self, source_hash: str, entity_type: str) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO fetched (source_hash, entity_type, first_seen) VALUES (?, ?, ?)",
            (source_hash, entity_type, int(time.time() * 1000)),
        )
        self._conn.commit()

    def filter_new(self, candidates: list[tuple[str, str]]) -> list[tuple[str, str]]:
        """Given (source_hash, entity_type) pairs, return only those not yet seen."""
        if not candidates:
            return []
        placeholders = ",".join("?" * len(candidates))
        hashes = [h for h, _ in candidates]
        seen_rows = self._conn.execute(
            f"SELECT source_hash FROM fetched WHERE source_hash IN ({placeholders})",
            hashes,
        ).fetchall()
        seen_set = {r[0] for r in seen_rows}
        return [(h, e) for h, e in candidates if h not in seen_set]

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "DedupStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
