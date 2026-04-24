"""Phase 5 — end-to-end voice loop.

Two modes:
  --file PATH    transcribe a pre-recorded WAV (no mic needed)
  --mic SECONDS  record from mic then answer (default mode; 5 s window)

Pipeline:
  (mic or file) → Whisper-large-v3-turbo (MLX)
              → RetrievalAgent (text query → top-k chunks)
              → LLMAgent (grounded answer + citations)
              → Kokoro-82M (TTS)
              → play back through speakers

Reports per-stage and total latency.
"""
from __future__ import annotations

import argparse
import logging
import sys
import tempfile
import time
from pathlib import Path

from actian_vectorai import VectorAIClient

from revvec import config
from revvec.embed.service import get_embedder
from revvec.llm.cache import AnswerCache
from revvec.llm.qwen_mlx import LLMAgent
from revvec.memory.actian_writer import MemoryAgent
from revvec.retrieval.hybrid import RetrievalAgent
from revvec.voice.stt_tts import get_voice_agent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("phase5_voice")


def run_once(
    *,
    wav_in: Path,
    persona: str,
    play_back: bool,
    client: VectorAIClient,
    voice,
    retrieval: RetrievalAgent,
    llm: LLMAgent,
    cache: AnswerCache,
    embedder,
) -> dict[str, float]:
    timings: dict[str, float] = {}
    t_total_start = time.perf_counter()

    # 1) ASR
    t0 = time.perf_counter()
    query, asr_ms = voice.transcribe(wav_in)
    timings["asr_ms"] = asr_ms
    print(f"\n  heard: {query!r}")

    if not query:
        print("  (empty transcription; aborting)")
        return timings

    # 2) Cache lookup
    t0 = time.perf_counter()
    q_emb = embedder.embed_text(query)[0].tolist()
    cached = cache.lookup(q_emb, persona)
    cache_ms = (time.perf_counter() - t0) * 1000
    timings["cache_lookup_ms"] = cache_ms

    if cached:
        answer = cached["answer"]
        print(f"  [cache HIT {cache_ms:.0f} ms]")
    else:
        # 3) Retrieve
        t0 = time.perf_counter()
        hits = retrieval.retrieve(query_text=query, persona=persona, limit=4)
        retrieve_ms = (time.perf_counter() - t0) * 1000
        timings["retrieve_ms"] = retrieve_ms

        if not hits:
            print("  (no retrieved context)")
            return timings

        # 4) Generate
        t0 = time.perf_counter()
        result = llm.generate(persona=persona, question=query, chunks=hits, max_tokens=120)
        gen_ms = (time.perf_counter() - t0) * 1000
        timings["generate_ms"] = gen_ms
        answer = result.answer

        # Write back to cache
        cache.write(q_emb, persona, query, answer, result.citations)

    print(f"  answer: {answer[:240]}")

    # 5) TTS
    t0 = time.perf_counter()
    wav_out, tts_ms = voice.speak(answer, out_path=Path(tempfile.gettempdir()) / "revvec_out.wav")
    timings["tts_ms"] = tts_ms

    total_ms = (time.perf_counter() - t_total_start) * 1000
    timings["total_ms"] = total_ms

    # 6) Playback (optional)
    if play_back:
        voice.play(wav_out)

    return timings


def main() -> int:
    parser = argparse.ArgumentParser()
    src = parser.add_mutually_exclusive_group()
    src.add_argument("--file", type=Path, help="use this WAV instead of recording")
    src.add_argument("--mic", type=float, default=None, help="record N seconds from the mic")
    parser.add_argument("--persona", default="maintenance",
                        choices=["new_hire", "maintenance", "quality", "plant_manager"])
    parser.add_argument("--play", action="store_true", help="play the synthesized answer")
    parser.add_argument("--repeat", type=int, default=1, help="run the loop N times (for latency stats)")
    args = parser.parse_args()

    # Warm everything so latency numbers aren't dominated by cold starts
    print("warming models (ASR / TTS / LLM / embed)...")
    voice = get_voice_agent()
    _ = voice._load_tts()
    embedder = get_embedder()
    _ = embedder.embed_text("warmup")
    llm = LLMAgent()
    _ = llm._load()
    print("warm.\n")

    # Decide input
    if args.file:
        wav_in = args.file
        if not wav_in.exists():
            sys.exit(f"no such file: {wav_in}")
    elif args.mic:
        print(f"recording {args.mic:.1f} seconds from mic — speak now…")
        wav_in = voice.record(seconds=args.mic)
    else:
        # Default: synthesize a canned demo query via Kokoro so we don't need a mic
        canned = "How does MEDA measure atmospheric pressure on Mars?"
        print(f"no --file / --mic given; using synthesized demo query: {canned!r}")
        wav_in, _ = voice.speak(canned, out_path=Path(tempfile.gettempdir()) / "revvec_demo_in.wav")

    # Run loop N times
    all_timings: list[dict[str, float]] = []
    with VectorAIClient(config.ACTIAN_URL) as client:
        client.connect()
        MemoryAgent(client).ensure_ready()
        retrieval = RetrievalAgent(client)
        cache = AnswerCache(client)

        for i in range(args.repeat):
            print(f"── run {i + 1}/{args.repeat} (persona={args.persona}) ──")
            timings = run_once(
                wav_in=wav_in,
                persona=args.persona,
                play_back=args.play,
                client=client,
                voice=voice,
                retrieval=retrieval,
                llm=llm,
                cache=cache,
                embedder=embedder,
            )
            all_timings.append(timings)

    # Latency summary
    print("\n=== per-stage latency summary ===")
    for k in ("asr_ms", "cache_lookup_ms", "retrieve_ms", "generate_ms", "tts_ms", "total_ms"):
        vals = [t[k] for t in all_timings if k in t]
        if not vals:
            continue
        vmin, vmax = min(vals), max(vals)
        vavg = sum(vals) / len(vals)
        print(f"  {k:18s}  n={len(vals):2d}  avg={vavg:6.0f} ms  min={vmin:6.0f}  max={vmax:6.0f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
