"""SensorIngestor, CMAPSS run-to-failure trajectories → Chronos-Bolt → sensor_vec.

CMAPSS format (space-separated):
  col 0   : engine unit number (1..N)
  col 1   : time in cycles
  cols 2-4: operating settings (3 values)
  cols 5-25: sensor readings (21 values, labelled sensor_1 .. sensor_21)

For each engine we take the LAST `window_size` cycles, the final degradation
phase leading to failure, and embed one or more sensor channels. Each channel
yields a separate sensor_vec point (entity_type=sensor_window) so the
ClusterAgent (Phase 2b) can promote recurring failure fingerprints.

Sensor column 7 (HPC outlet temperature) is one of the classic predictive
signals in the CMAPSS literature, we default to it.
"""
from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path
from typing import Iterable

import numpy as np
from actian_vectorai import PointStruct

from revvec import config
from revvec.embed.service import EmbedAgent, get_embedder
from revvec.ingestion.dedup import DedupStore
from revvec.memory.actian_writer import MemoryAgent

log = logging.getLogger(__name__)


# CMAPSS: 0=unit, 1=cycle, 2-4=op_settings, 5-25=sensors → sensor_n (1-indexed) at col 4+n
SENSOR_COL_BASE = 4
DEFAULT_SENSOR_CHANNELS: tuple[int, ...] = (7, 11)  # HPC outlet temp, HPC outlet static pressure


class SensorIngestor:
    def __init__(
        self,
        memory: MemoryAgent,
        embedder: EmbedAgent | None = None,
        dedup: DedupStore | None = None,
        window_size: int = 60,
        sensor_channels: Iterable[int] = DEFAULT_SENSOR_CHANNELS,
        max_engines: int | None = None,
    ) -> None:
        self.memory = memory
        self.embedder = embedder or get_embedder()
        self.dedup = dedup or DedupStore(config.REVVEC_DATA / "dedup.sqlite")
        self.window_size = window_size
        self.sensor_channels = tuple(sensor_channels)
        self.max_engines = max_engines

    def ingest_cmapss_train_file(self, path: Path, subdataset: str) -> int:
        """Ingest one CMAPSS train_FDxxx.txt file. Returns new points written."""
        if not path.exists():
            log.warning("sensor_ingest: missing file %s", path)
            return 0

        log.info("sensor_ingest: parsing %s", path.name)
        data = np.loadtxt(str(path))
        n_engines = int(data[:, 0].max())
        if self.max_engines:
            n_engines = min(n_engines, self.max_engines)
        log.info("sensor_ingest: %d engines in %s", n_engines, subdataset)

        now_ms = int(time.time() * 1000)
        all_points: list[PointStruct] = []
        all_marks: list[tuple[str, str]] = []

        for engine_id in range(1, n_engines + 1):
            engine_rows = data[data[:, 0] == engine_id]
            if len(engine_rows) < self.window_size:
                continue
            window_rows = engine_rows[-self.window_size :]  # last N cycles = end-of-life

            # Batch-embed all channels for this engine
            windows_per_channel: list[np.ndarray] = []
            channel_ids: list[int] = []
            source_hashes: list[str] = []
            for ch in self.sensor_channels:
                src_hash = f"cmapss:{subdataset}:engine_{engine_id:03d}:sensor_{ch}"
                if self.dedup.seen(src_hash):
                    continue
                col_idx = SENSOR_COL_BASE + ch
                window = window_rows[:, col_idx].astype(np.float32)
                windows_per_channel.append(window)
                channel_ids.append(ch)
                source_hashes.append(src_hash)

            if not windows_per_channel:
                continue

            vecs = self.embedder.embed_sensor(np.stack(windows_per_channel))  # (n_channels, 512)

            for ch, src_hash, vec in zip(channel_ids, source_hashes, vecs):
                payload = {
                    "entity_type": "sensor_window",
                    "entity_id": str(uuid.uuid4()),
                    "source": f"cmapss/{subdataset}",
                    "source_hash": src_hash,
                    "modality": "sensor",
                    "timestamp_ms": now_ms,
                    "ingested_ms": now_ms,
                    "author_id": "nasa-cmapss",
                    "classification": "public",
                    "state": "active",
                    "role_visibility": ["maintenance", "quality", "plant_manager"],
                    "equipment_id": f"turbofan_{subdataset}_{engine_id:03d}",
                    "severity": 4,  # end-of-life is max severity
                    "text_preview": (
                        f"Engine {engine_id} ({subdataset}), final {self.window_size} "
                        f"cycles of sensor_{ch} trajectory"
                    ),
                    "title": f"CMAPSS {subdataset} engine {engine_id:03d} sensor_{ch}",
                }
                all_points.append(PointStruct(
                    id=payload["entity_id"],
                    vector={"sensor_vec": vec.tolist()},
                    payload=payload,
                ))
                all_marks.append((src_hash, "sensor_window"))

        if not all_points:
            log.info("sensor_ingest: 0 fresh sensor windows from %s", subdataset)
            return 0

        written = self.memory.upsert(all_points)
        for src_hash, et in all_marks:
            self.dedup.mark(src_hash, et)

        log.info("sensor_ingest: wrote %d sensor_vec points from %s (%d engines × %d channels)",
                 written, subdataset, n_engines, len(self.sensor_channels))
        return written

    def ingest_cmapss_directory(self, cmapss_dir: Path) -> int:
        """Ingest all train_FD*.txt files under a CMAPSS extracted directory."""
        total = 0
        for sub in ["FD001", "FD002", "FD003", "FD004"]:
            path = cmapss_dir / f"train_{sub}.txt"
            if not path.exists():
                continue
            total += self.ingest_cmapss_train_file(path, sub)
        return total
