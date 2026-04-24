"""Phase 3 retrieval gate — golden queries against real NASA corpus.

Requires a live Actian with the Phase-1/2 corpus already ingested. Marked
`slow` so the fast-test suite skips it.
"""
from __future__ import annotations

import time

import pytest
from actian_vectorai import VectorAIClient

from revvec import config
from revvec.memory.actian_writer import MemoryAgent
from revvec.retrieval.hybrid import RetrievalAgent


GOLDEN_QUERIES: list[tuple[str, list[str]]] = [
    # (query, list of substrings at least one of which must appear in a top-3 title)
    ("How does MEDA measure atmospheric pressure on Mars?",
     ["MEDA", "Atmospheric", "Mars"]),
    ("SuperCam analysis of the igneous Maaz Formation",
     ["SuperCam", "Maaz", "Igneous"]),
    ("Mars 2020 entry descent landing performance",
     ["Entry, Descent", "EDL", "MEDLI"]),
    ("Apollo lunar module anomaly investigation",
     ["Apollo", "lunar module", "anomaly"]),
]


@pytest.mark.slow
def test_golden_set_top3_contains_expected_term():
    with VectorAIClient(config.ACTIAN_URL) as c:
        c.connect()
        MemoryAgent(c).ensure_ready()
        agent = RetrievalAgent(c)
        _ = agent.embedder.embed_text("warmup")

        failures: list[str] = []
        for query, expected_any in GOLDEN_QUERIES:
            hits = agent.retrieve(query_text=query, limit=3)
            joined_titles = " | ".join(h.title for h in hits)
            found = any(any(term.lower() in h.title.lower() for term in expected_any) for h in hits)
            if not found:
                failures.append(f"query={query!r} expected any of {expected_any} in top-3: {joined_titles}")
        assert not failures, "\n".join(failures)


@pytest.mark.slow
def test_retrieval_p95_under_800ms():
    with VectorAIClient(config.ACTIAN_URL) as c:
        c.connect()
        MemoryAgent(c).ensure_ready()
        agent = RetrievalAgent(c)
        _ = agent.embedder.embed_text("warmup")

        latencies: list[float] = []
        for query, _ in GOLDEN_QUERIES:
            t0 = time.perf_counter()
            agent.retrieve(query_text=query, limit=6)
            latencies.append((time.perf_counter() - t0) * 1000)

        p95 = sorted(latencies)[int(len(latencies) * 0.95)] if len(latencies) > 1 else latencies[0]
        assert p95 < 800.0, f"P95 {p95:.0f}ms exceeds 800ms budget; raw={latencies}"
