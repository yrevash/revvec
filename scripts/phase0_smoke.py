"""Phase 0 smoke test.

Validates:
  1. Actian server reachable on ACTIAN_URL
  2. Collection creation with 4 named vectors works (text/page/photo/sensor)
  3. One point with all 4 named vectors can be upserted
  4. Each named vector can be searched independently

Exit code 0 on success with "PHASE-0 OK". Target wall time: <3s on M-series.
"""
from __future__ import annotations

import sys
import time
import uuid

from actian_vectorai import PointStruct, VectorAIClient

from revvec import config
from revvec.memory.schema import build_vectors_config

COLLECTION = "phase0_smoke"


def make_dummy_vector(dim: int) -> list[float]:
    return [0.01 * (i % 7) for i in range(dim)]


def main() -> int:
    t0 = time.perf_counter()
    errors: list[str] = []

    try:
        with VectorAIClient(config.ACTIAN_URL) as client:
            info = client.health_check()
            print(f"  server: {info.get('title', 'unknown')} v{info.get('version', '?')}")

            if client.collections.exists(COLLECTION):
                client.collections.delete(COLLECTION)

            client.collections.create(COLLECTION, vectors_config=build_vectors_config())

            point_id = str(uuid.uuid4())
            vectors = {
                "text_vec":   make_dummy_vector(config.DIM_TEXT),
                "photo_vec":  make_dummy_vector(config.DIM_PHOTO),
                "sensor_vec": make_dummy_vector(config.DIM_SENSOR),
            }
            client.points.upsert(COLLECTION, [
                PointStruct(
                    id=point_id,
                    vector=vectors,
                    payload={"entity_type": "smoke", "hello": "revvec"},
                ),
            ])

            for vname, dim in [
                ("text_vec",   config.DIM_TEXT),
                ("photo_vec",  config.DIM_PHOTO),
                ("sensor_vec", config.DIM_SENSOR),
            ]:
                hits = client.points.search(
                    COLLECTION,
                    vector=make_dummy_vector(dim),
                    using=vname,
                    limit=1,
                )
                if not hits or str(hits[0].id) != point_id:
                    errors.append(f"retrieval failed on {vname}")
                else:
                    print(f"  retrieved via {vname} (dim={dim}): score={hits[0].score:.4f}")

            client.collections.delete(COLLECTION)

    except Exception as e:  # noqa: BLE001
        errors.append(f"exception: {e!r}")

    dt_ms = (time.perf_counter() - t0) * 1000
    if errors:
        print(f"PHASE-0 FAIL ({dt_ms:.0f}ms)")
        for err in errors:
            print(f"  - {err}")
        return 1

    print(f"PHASE-0 OK ({dt_ms:.0f}ms)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
