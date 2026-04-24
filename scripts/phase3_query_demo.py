"""Phase 3 — retrieval demo.

Runs 4 persona-flavoured queries against the real 1938-point NASA corpus,
reports top hits + latency. Eyeball test for whether the three-tier pipeline
produces sensible top-1 matches.
"""
from __future__ import annotations

import logging
import sys
import time
from typing import Iterable

from actian_vectorai import VectorAIClient

from revvec import config
from revvec.memory.actian_writer import MemoryAgent
from revvec.retrieval.hybrid import RetrievalAgent, RetrievalHit

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("phase3_query")


PERSONA_QUERIES: list[tuple[str, str, str]] = [
    # (persona, human label, query text)
    ("new_hire",      "how does MEDA measure atmospheric pressure?",
                     "How does the MEDA instrument measure atmospheric pressure on Mars?"),
    ("maintenance",   "what caused Apollo 13 oxygen tank failure?",
                     "What was the root cause of the Apollo 13 oxygen tank anomaly?"),
    ("quality",       "SuperCam igneous Maaz formation",
                     "SuperCam analysis of the igneous Maaz Formation"),
    ("plant_manager", "Perseverance rover entry descent landing",
                     "Perseverance entry descent landing performance review"),
]


def _truncate(s: str, n: int = 90) -> str:
    s = s.replace("\n", " ").strip()
    return s[:n] + ("…" if len(s) > n else "")


def print_hits(persona: str, label: str, hits: list[RetrievalHit]) -> None:
    print(f"\n── persona={persona}  :: {label}")
    if not hits:
        print("    (no hits)")
        return
    for i, h in enumerate(hits, 1):
        print(f"  {i}. semantic={h.score_semantic:.3f}  "
              f"lex={h.score_lexical:.3f}  "
              f"final={h.score_final:.3f}  "
              f"{h.payload.get('entity_type', '?'):18s}  "
              f"{_truncate(h.title, 70)}")


def main() -> int:
    latencies: list[float] = []
    with VectorAIClient(config.ACTIAN_URL) as client:
        client.connect()
        memory = MemoryAgent(client)
        memory.ensure_ready()

        agent = RetrievalAgent(client)

        # Warm the embedder so first query's latency is honest (no model-load)
        _ = agent.embedder.embed_text("warmup")

        for persona, label, query in PERSONA_QUERIES:
            t0 = time.perf_counter()
            hits = agent.retrieve(query_text=query, persona=persona, limit=4)
            dt_ms = (time.perf_counter() - t0) * 1000
            latencies.append(dt_ms)
            print_hits(persona, f"[{dt_ms:.0f} ms] {label}", hits)

    print("\n=== latency summary (after warmup) ===")
    if latencies:
        latencies_sorted = sorted(latencies)
        p50 = latencies_sorted[len(latencies_sorted) // 2]
        p95 = latencies_sorted[int(len(latencies_sorted) * 0.95)] if len(latencies_sorted) > 1 else latencies_sorted[0]
        print(f"  n={len(latencies)}  p50={p50:.0f} ms  p95={p95:.0f} ms  "
              f"min={min(latencies):.0f} ms  max={max(latencies):.0f} ms")
    return 0


if __name__ == "__main__":
    sys.exit(main())
