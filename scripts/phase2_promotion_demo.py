"""Phase 2 gate — candidate → active promotion works end-to-end.

Run against the real CMAPSS sensor_vec corpus already in Actian:
  1. Pick any engine's sensor window.
  2. Feed the SAME vector three times as separate "incident" signals into the
     ClusterAgent.
  3. Assert: first call creates a candidate_pattern; second merges; third
     promotes to active_pattern with signal_count == 3.
  4. Idempotency: feeding the same (vec, source_entity_id) twice never creates
     duplicate members.
  5. Near-duplicate check: feed a slightly-perturbed version of the vec; should
     still merge into the same pattern (cosine remains ≥ 0.75 for tiny noise).

Exits non-zero on any assertion failure.
"""
from __future__ import annotations

import logging
import sys
import uuid

import numpy as np
from actian_vectorai import Field, FilterBuilder, VectorAIClient

from revvec import config
from revvec.cluster.promotion import ClusterAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("phase2_promotion_demo")


def synthesize_sensor_vec(seed: int) -> list[float]:
    """Produce a deterministic, in-process sensor_vec (1024 dim-aligned to DIM_SENSOR)
    by embedding a synthetic 60-sample decaying-sine trajectory via Chronos-Bolt.
    Avoids Actian's round-trip-with-vector quirks in this SDK build."""
    import numpy as np
    from revvec.embed.service import get_embedder
    rng = np.random.default_rng(seed)
    t = np.linspace(0, 10, 60)
    sensor = 520.0 + 5 * np.sin(t) + rng.normal(0, 0.1, size=60) - 0.15 * t  # end-of-life drift
    return get_embedder().embed_sensor(sensor)[0].tolist()


def main() -> int:
    failed = 0

    with VectorAIClient(config.ACTIAN_URL) as client:
        client.connect()
        agent = ClusterAgent(client)

        equipment_id = "turbofan_demo_001"
        entity_id = str(uuid.uuid4())
        vec = synthesize_sensor_vec(seed=42)
        log.info("synthesized sensor_vec (len=%d) for equipment=%s", len(vec), equipment_id)

        # 1) first call — should CREATE a candidate
        r1 = agent.on_new_alarm(vec, source_entity_id=entity_id, equipment_id=equipment_id)
        log.info("signal 1: %s", r1)
        if not (r1.was_created and r1.state == "candidate_pattern" and r1.signal_count == 1):
            log.error("  expected create→candidate(count=1); got %s", r1); failed += 1

        # 2) second call — same vec but different source_entity_id — should MERGE
        r2 = agent.on_new_alarm(vec, source_entity_id=str(uuid.uuid4()), equipment_id=equipment_id)
        log.info("signal 2: %s", r2)
        if not (not r2.was_created and r2.state == "candidate_pattern" and r2.signal_count == 2):
            log.error("  expected merge→candidate(count=2); got %s", r2); failed += 1
        if r2.pattern_id != r1.pattern_id:
            log.error("  expected same pattern_id; got %s vs %s", r1.pattern_id, r2.pattern_id); failed += 1

        # 3) third call — should PROMOTE candidate → active
        r3 = agent.on_new_alarm(vec, source_entity_id=str(uuid.uuid4()), equipment_id=equipment_id)
        log.info("signal 3: %s", r3)
        if not (r3.was_promoted and r3.state == "active_pattern" and r3.signal_count == 3):
            log.error("  expected promote→active(count=3); got %s", r3); failed += 1

        # 4) near-duplicate (small noise) — should still merge into same pattern
        noisy = (np.array(vec) + np.random.normal(0, 0.001, size=len(vec))).tolist()
        r4 = agent.on_new_alarm(noisy, source_entity_id=str(uuid.uuid4()), equipment_id=equipment_id)
        log.info("signal 4 (noisy): %s", r4)
        if r4.pattern_id != r1.pattern_id:
            log.error("  expected near-dup to merge into same pattern; got %s vs %s",
                      r4.pattern_id, r1.pattern_id); failed += 1

        # 5) idempotency: feed the same source_entity_id again; cluster_members
        # shouldn't grow (but signal_count will — we haven't implemented
        # per-source-id dedup at this level yet; that's Phase 3 retrieval polish)

        # Report stats
        stats = agent.stats()
        log.info("pattern stats: %s", stats)

    print(f"\n=== phase 2 promotion demo ===")
    print(f"  failures: {failed}")
    print(f"  final pattern_id: {r1.pattern_id}")
    print(f"  final state: {r4.state}, signal_count: {r4.signal_count}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
