"""Phase 4 — end-to-end grounded answers with citations.

For each persona-flavoured golden query:
  1. Retrieve top-4 chunks via RetrievalAgent (reuses Phase-3 pipeline).
  2. LLMAgent grounds on those chunks, emits "[source:N]" citations.
  3. Resolve citations → real entity_ids (no fabrication check).
  4. Write back to answer_cache. Re-ask the same query → cache hit.

Gate (reported at end):
  - 4/4 answers cite real entity_ids
  - cache hit under 150 ms
"""
from __future__ import annotations

import logging
import sys
import time

from actian_vectorai import VectorAIClient

from revvec import config
from revvec.embed.service import get_embedder
from revvec.llm.cache import AnswerCache
from revvec.llm.qwen_mlx import LLMAgent
from revvec.memory.actian_writer import MemoryAgent
from revvec.retrieval.hybrid import RetrievalAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("phase4_answer")


PERSONA_QUERIES: list[tuple[str, str, str]] = [
    ("new_hire",      "MEDA pressure",
                     "How does MEDA measure atmospheric pressure on Mars?"),
    ("maintenance",   "Apollo lunar module anomaly",
                     "What caused the Apollo lunar module propellant gauge anomaly?"),
    ("quality",       "SuperCam Maaz",
                     "What did SuperCam find about the Maaz formation?"),
    ("plant_manager", "Perseverance EDL",
                     "Summarise Mars 2020 Perseverance entry, descent, and landing performance."),
]


def _truncate(s: str, n: int = 120) -> str:
    s = s.replace("\n", " ").strip()
    return s[:n] + ("…" if len(s) > n else "")


def main() -> int:
    fabricated_fails = 0
    with VectorAIClient(config.ACTIAN_URL) as client:
        client.connect()
        memory = MemoryAgent(client)
        memory.ensure_ready()

        embedder = get_embedder()
        retrieval = RetrievalAgent(client)
        llm = LLMAgent()
        cache = AnswerCache(client)

        # Warm everything so first query doesn't pay model-load time.
        log.info("warming models...")
        _ = embedder.embed_text("warmup")
        _ = llm._load()
        log.info("warmup done")

        cache_hit_latencies: list[float] = []
        for persona, label, question in PERSONA_QUERIES:
            print(f"\n══ persona={persona} :: {label} ══")
            print(f"Q: {question}")

            # First pass — miss the cache, generate
            q_emb = embedder.embed_text(question)[0].tolist()
            t_cache = time.perf_counter()
            cached = cache.lookup(q_emb, persona)
            cache_ms = (time.perf_counter() - t_cache) * 1000
            print(f"  [cache lookup {cache_ms:.0f} ms → {'HIT' if cached else 'miss'}]")

            if cached:
                answer = cached["answer"]
                print(f"A (cached): {_truncate(answer, 300)}")
                continue

            t_retr = time.perf_counter()
            hits = retrieval.retrieve(query_text=question, persona=persona, limit=4)
            retr_ms = (time.perf_counter() - t_retr) * 1000
            if not hits:
                print("  (no retrieved context)")
                continue
            print(f"  [retrieved {len(hits)} chunks in {retr_ms:.0f} ms]")

            t_gen = time.perf_counter()
            result = llm.generate(persona=persona, question=question, chunks=hits, max_tokens=160)
            gen_ms = (time.perf_counter() - t_gen) * 1000
            print(f"A ({gen_ms:.0f} ms): {_truncate(result.answer, 300)}")
            for c in result.citations:
                tag = "OK" if c.entity_id else "FABRICATED"
                print(f"    [{tag}] [source:{c.index}] → {_truncate(c.title, 70)}")

            if result.has_fabricated_citations:
                fabricated_fails += 1

            cache.write(q_emb, persona, question, result.answer, result.citations)

        # Second pass — every query should cache-hit now
        print("\n══ cache re-run (should all HIT) ══")
        for persona, label, question in PERSONA_QUERIES:
            q_emb = embedder.embed_text(question)[0].tolist()
            t0 = time.perf_counter()
            cached = cache.lookup(q_emb, persona)
            dt_ms = (time.perf_counter() - t0) * 1000
            cache_hit_latencies.append(dt_ms)
            status = "HIT" if cached else "MISS"
            print(f"  {persona:14s} {status}  {dt_ms:.0f} ms   {_truncate(question, 70)}")

    if cache_hit_latencies:
        p95 = sorted(cache_hit_latencies)[int(len(cache_hit_latencies) * 0.95)] if len(cache_hit_latencies) > 1 else cache_hit_latencies[0]
        print(f"\ncache hit p95: {p95:.0f} ms  (target <150)")
    print(f"fabricated-citation failures: {fabricated_fails}")
    return 0 if fabricated_fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
