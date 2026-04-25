"""FastAPI server exposing revvec's agents to the Tauri app.

Run:
    python -m revvec.server           # bind 127.0.0.1:8000

Tauri launches this as a sidecar in dev (`beforeDevCommand` in tauri.conf.json)
and in prod (bundled executable via PyInstaller/shiv at Phase-9 submission).
"""
from __future__ import annotations

import hashlib
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from actian_vectorai import Field, FilterBuilder, VectorAIClient
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from revvec import __version__, config
from revvec.audit.chain import AuditAgent
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
log = logging.getLogger("revvec.server")

app = FastAPI(title="revvec", version=__version__)

# Tauri webview runs on tauri://localhost; allow everything for local dev.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── lazy-init shared state ─────────────────────────────────────────────────


class _State:
    client: VectorAIClient | None = None
    memory: MemoryAgent | None = None
    retrieval: RetrievalAgent | None = None
    cache: AnswerCache | None = None
    llm: LLMAgent | None = None
    audit: AuditAgent = AuditAgent(config.REVVEC_DATA / "audit")
    # VoiceAgent is lazy-imported only on /api/voice to avoid loading Kokoro's
    # spaCy dep at server startup


state = _State()


def _ensure_client() -> VectorAIClient:
    if state.client is None:
        c = VectorAIClient(config.ACTIAN_URL)
        c.connect()
        state.client = c
        state.memory = MemoryAgent(c)
        state.memory.ensure_ready()
        state.retrieval = RetrievalAgent(c)
        state.cache = AnswerCache(c)
    return state.client


def _ensure_llm() -> LLMAgent:
    if state.llm is None:
        state.llm = LLMAgent()
        _ = state.llm._load()  # warm
    return state.llm


# ─── /api/health ────────────────────────────────────────────────────────────


@app.get("/api/health")
async def health() -> dict[str, Any]:
    try:
        c = _ensure_client()
        n = c.points.count(config.COLLECTION)
        reachable = True
    except Exception as e:  # noqa: BLE001
        reachable = False
        n = 0
        log.warning("actian health check failed: %r", e)

    return {
        "ok": reachable,
        "version": __version__,
        "actian": {
            "reachable": reachable,
            "collection": config.COLLECTION,
            "points": n,
        },
        "models": {
            "text":   config.TEXT_EMBED_MODEL,
            "photo":  config.PHOTO_EMBED_MODEL,
            "sensor": config.SENSOR_EMBED_MODEL,
            "llm":    config.LLM_MODEL,
            "asr":    config.ASR_MODEL,
            "tts":    config.TTS_MODEL,
        },
    }


# ─── /api/source/{entity_id} ────────────────────────────────────────────────


CACHE_DIR = config.REVVEC_DATA / "fetch_cache"


def _find_cached_pdf(payload: dict[str, Any]) -> tuple[Path | None, int | None]:
    """Given a point's payload, resolve (local_pdf_path, page_num)."""
    url = str(payload.get("source") or "")
    source_hash = str(payload.get("source_hash") or "")
    # page number is the suffix after ':page_' in source_hash
    page_num: int | None = None
    if ":page_" in source_hash:
        try:
            page_num = int(source_hash.rsplit(":page_", 1)[-1])
        except ValueError:
            page_num = None

    if not url:
        return None, page_num
    # Our fetch.py caches by sha256(url)
    url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()
    ext = os.path.splitext(urlparse(url).path)[1].lower() or ".pdf"
    p = CACHE_DIR / f"{url_hash}{ext}"
    if p.exists():
        return p, page_num
    return None, page_num


@app.get("/api/source/{entity_id}/meta")
async def source_meta(entity_id: str) -> dict[str, Any]:
    c = _ensure_client()
    pts = c.points.get(config.COLLECTION, ids=[entity_id], with_payload=True)
    if not pts:
        # Fall back: some UUIDs returned via the search API are str(int), try filter lookup
        f = FilterBuilder().must(Field("entity_id").eq(entity_id)).build()
        dummy = [0.0] * config.DIM_TEXT
        hits = c.points.search(config.COLLECTION, vector=dummy, using="text_vec", limit=1, filter=f, with_payload=True)
        if not hits:
            raise HTTPException(status_code=404, detail=f"no point with entity_id={entity_id}")
        payload = hits[0].payload
    else:
        payload = pts[0].payload
    pdf_path, page = _find_cached_pdf(payload)
    return {
        "entity_type": payload.get("entity_type"),
        "title": payload.get("title"),
        "text_preview": payload.get("text_preview"),
        "source_url": payload.get("source"),
        "page": page,
        "has_pdf": pdf_path is not None,
    }


@app.get("/api/source/{entity_id}/pdf")
async def source_pdf(entity_id: str) -> FileResponse:
    c = _ensure_client()
    pts = c.points.get(config.COLLECTION, ids=[entity_id], with_payload=True)
    if not pts:
        f = FilterBuilder().must(Field("entity_id").eq(entity_id)).build()
        dummy = [0.0] * config.DIM_TEXT
        hits = c.points.search(config.COLLECTION, vector=dummy, using="text_vec", limit=1, filter=f, with_payload=True)
        if not hits:
            raise HTTPException(status_code=404, detail="not found")
        payload = hits[0].payload
    else:
        payload = pts[0].payload
    pdf_path, _ = _find_cached_pdf(payload)
    if pdf_path is None:
        raise HTTPException(status_code=404, detail="no cached PDF for this entity")
    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        headers={"Cache-Control": "public, max-age=3600"},
    )


# ─── /api/query ─────────────────────────────────────────────────────────────


class HistoryTurn(BaseModel):
    role: str
    content: str


class UserProfile(BaseModel):
    role: str | None = None
    experience: str | None = None
    focus: str | None = None
    preferences: str | None = None
    notes: str | None = None


class QueryRequest(BaseModel):
    query_text: str
    persona: str = "maintenance"
    limit: int = 4
    use_cache: bool = True
    history: list[HistoryTurn] | None = None
    user_profile: UserProfile | None = None


def _profile_dict(p: UserProfile | None) -> dict[str, str] | None:
    if p is None:
        return None
    d = {k: (v or "").strip() for k, v in p.model_dump().items() if (v or "").strip()}
    return d or None


def _actian_block(
    *,
    path: str,
    vectors: list[str],
    actian_ms: float,
    rerank_ms: float = 0.0,
    hits_used: int = 0,
    top_score: float | None = None,
    summary: str = "",
    operation: str = "",
) -> dict[str, Any]:
    return {
        "path": path,
        "vectors": vectors,
        "actian_ms": round(actian_ms, 1),
        "rerank_ms": round(rerank_ms, 1),
        "hits_used": hits_used,
        "top_score": top_score,
        "summary": summary,
        "operation": operation,
    }


# When the top retrieved hit's semantic similarity is below this, we bypass
# grounded generation and fall through to LLMAgent.generate_general().
# Lowered from 0.50 → 0.20 so voice transcripts (which embed slightly
# differently than typed text) still take the grounded RAG path.
GENERAL_FALLBACK_THRESHOLD = 0.20

# Obvious non-query inputs that always get the general path, regardless of score.
_GREETINGS: frozenset[str] = frozenset({
    "hi", "hello", "hey", "yo", "hola", "sup", "howdy", "test", "testing",
    "ping", "?", "ok", "thanks", "thank you", "bye", "good morning", "good night",
})


def _is_greeting(q: str) -> bool:
    qn = q.strip().lower().rstrip("!.? ")
    return len(qn) < 4 or qn in _GREETINGS


@app.post("/api/query")
async def query_endpoint(req: QueryRequest) -> dict[str, Any]:
    # IMPORTANT: must be async def. MLX's GPU stream is thread-local and breaks
    # if FastAPI pushes this handler to its default worker threadpool (the code
    # was initialised in the main thread). Making the handler async pins it to
    # the event loop; the blocking retrieval + LLM work is fine for a
    # single-user desktop app.
    c = _ensure_client()
    embedder = get_embedder()
    timings: dict[str, float] = {}
    t_total = time.perf_counter()

    # 1) cache lookup, disabled when follow-up history OR a user_profile is
    # present, so the cache doesn't bleed a stale one-off answer into a
    # continuing conversation or across users with different contexts.
    has_history = bool(req.history)
    profile = _profile_dict(req.user_profile)
    has_profile = profile is not None
    q_emb = embedder.embed_text(req.query_text)[0].tolist()
    t0 = time.perf_counter()
    cached = (
        state.cache.lookup(q_emb, req.persona)
        if (req.use_cache and not has_history and not has_profile)
        else None
    )
    timings["cache_lookup"] = (time.perf_counter() - t0) * 1000

    if cached:
        import json as _json
        cites_raw = cached.get("citations_json") or "[]"
        try:
            cites = _json.loads(cites_raw)
        except Exception:  # noqa: BLE001
            cites = []
        timings["total"] = (time.perf_counter() - t_total) * 1000
        state.audit.record({
            "action": "query",
            "persona": req.persona,
            "query": req.query_text[:500],
            "from_cache": True,
            "general_mode": False,
            "citation_count": len(cites),
            "total_ms": round(timings["total"], 1),
        })
        return {
            "answer": cached["answer"],
            "citations": cites,
            "from_cache": True,
            "persona": req.persona,
            "retrieved": 0,
            "timings_ms": timings,
            "actian": _actian_block(
                path="cache",
                vectors=["text_vec"],
                actian_ms=timings["cache_lookup"],
                summary="answer cache hit · cosine ≥ 0.95",
                operation="points.search(using=text_vec, score_threshold=0.95, filter=entity_type=answer_cache)",
            ),
        }

    # 2) retrieve
    t0 = time.perf_counter()
    hits = state.retrieval.retrieve(query_text=req.query_text, persona=req.persona, limit=req.limit)
    timings["retrieve"] = (time.perf_counter() - t0) * 1000

    llm = _ensure_llm()
    top_score = hits[0].score_semantic if hits else 0.0
    weak_retrieval = (
        _is_greeting(req.query_text)
        or (not hits)
        or (top_score < GENERAL_FALLBACK_THRESHOLD)
    )

    if weak_retrieval:
        # Fall through to general-knowledge mode, clearly labelled "(from model knowledge)"
        t0 = time.perf_counter()
        history_dicts = [h.model_dump() for h in (req.history or [])]
        result = llm.generate_general(
            req.persona, req.query_text, max_tokens=2048, history=history_dicts,
            user_profile=profile,
        )
        timings["generate"] = (time.perf_counter() - t0) * 1000
        timings["total"] = (time.perf_counter() - t_total) * 1000
        state.audit.record({
            "action": "query",
            "persona": req.persona,
            "query": req.query_text[:500],
            "retrieved": len(hits),
            "top_score": round(top_score, 4),
            "from_cache": False,
            "general_mode": True,
            "citation_count": 0,
            "total_ms": round(timings["total"], 1),
        })
        return {
            "answer": result.answer,
            "citations": [],
            "from_cache": False,
            "persona": req.persona,
            "retrieved": len(hits),
            "top_score": round(top_score, 4),
            "general_mode": True,
            "timings_ms": timings,
            "actian": _actian_block(
                path="general",
                vectors=["text_vec"],
                actian_ms=timings.get("retrieve", 0.0),
                hits_used=len(hits),
                top_score=round(top_score, 4) if hits else None,
                summary="no strong match · model knowledge fallback",
                operation="points.search(using=text_vec, limit=200) → top score below threshold",
            ),
        }

    # 3) grounded generate
    t0 = time.perf_counter()
    history_dicts = [h.model_dump() for h in (req.history or [])]
    result = llm.generate(
        persona=req.persona, question=req.query_text, chunks=hits,
        max_tokens=2048, history=history_dicts, user_profile=profile,
    )
    timings["generate"] = (time.perf_counter() - t0) * 1000

    # 4) write back to cache (best-effort). Skip for multi-turn or when a user
    # profile is set, so context-sensitive answers can't leak across users.
    if not has_history and not has_profile:
        try:
            state.cache.write(q_emb, req.persona, req.query_text, result.answer, result.citations)
        except Exception as e:  # noqa: BLE001
            log.warning("cache write failed: %r", e)

    timings["total"] = (time.perf_counter() - t_total) * 1000
    resp = {
        "answer": result.answer,
        "citations": [
            {"index": c.index, "entity_id": c.entity_id, "title": c.title, "preview": c.preview}
            for c in result.citations
        ],
        "from_cache": False,
        "persona": req.persona,
        "retrieved": len(hits),
        "top_score": round(top_score, 4),
        "general_mode": False,
        "timings_ms": timings,
        "actian": _actian_block(
            path="search",
            vectors=["text_vec"],
            actian_ms=timings.get("retrieve", 0.0),
            hits_used=len(hits),
            top_score=round(top_score, 4),
            summary=f"single-vector search · {len(hits)} chunks · BM25 rerank",
            operation="points.search(using=text_vec, limit=200) → stage 2: Okapi BM25 (industrial-code-aware tokenizer), 0.7·cosine + 0.3·BM25",
        ),
    }
    state.audit.record({
        "action": "query",
        "persona": req.persona,
        "query": req.query_text[:500],
        "retrieved": len(hits),
        "top_score": round(top_score, 4),
        "from_cache": False,
        "general_mode": False,
        "citation_count": len(result.citations),
        "total_ms": round(timings["total"], 1),
    })
    return resp


# ─── /api/voice (stretch, wired but not yet exercised via UI) ──────────────


@app.post("/api/voice")
async def voice_endpoint(
    audio: UploadFile = File(...),
    persona: str = Form("maintenance"),
) -> dict[str, Any]:
    """Accept an uploaded WAV/WebM (original path, kept for any client that
    can use the browser mic). Most clients should prefer /api/voice/live."""
    import tempfile
    from revvec.voice.stt_tts import get_voice_agent
    import base64

    voice = get_voice_agent()
    wav_in = Path(tempfile.mktemp(suffix=".wav"))
    wav_in.write_bytes(await audio.read())

    transcript, asr_ms = voice.transcribe(wav_in)
    timings: dict[str, float] = {"asr": asr_ms}

    if not transcript:
        return {"transcript": "", "error": "empty transcription", "timings_ms": timings}

    q = QueryRequest(query_text=transcript, persona=persona)
    qresp = await query_endpoint(q)
    timings.update(qresp["timings_ms"])

    t0 = time.perf_counter()
    wav_out, tts_ms = voice.speak(qresp["answer"])
    timings["tts"] = tts_ms
    timings["total"] = timings.get("total", 0) + asr_ms + tts_ms
    audio_b64 = base64.b64encode(wav_out.read_bytes()).decode()

    return {
        **qresp,
        "transcript": transcript,
        "answer_audio_b64": audio_b64,
        "timings_ms": timings,
    }


class LiveVoiceRequest(BaseModel):
    persona: str = "maintenance"
    seconds: float = 5.0


@app.post("/api/voice/stream")
async def voice_stream(req: LiveVoiceRequest) -> StreamingResponse:
    """Record `seconds` via sounddevice in chunks, emitting partial transcripts
    as SSE frames so the UI can populate the input field live.

    Events:
      - partial : { text }            (may repeat, text is the running transcript)
      - final   : { text, asr_ms }
      - error   : { message }
    """
    import asyncio
    import tempfile as _tempfile
    import threading
    import numpy as np
    from pathlib import Path as _Path

    async def gen():
        try:
            import sounddevice as sd  # noqa: F401
            import soundfile as sf  # noqa: F401
        except Exception as e:  # noqa: BLE001
            yield _sse({"event": "error", "message": f"audio stack unavailable: {e!r}"})
            return

        from revvec.voice.stt_tts import get_voice_agent, MIC_SAMPLE_RATE
        voice = get_voice_agent()

        chunk_sec = 0.6          # how often to emit a partial
        total_sec = float(req.seconds)
        buf_chunks: list[np.ndarray] = []
        buf_lock = threading.Lock()
        done_event = threading.Event()
        err_slot: dict[str, str] = {}

        def cb(indata, _frames, _time_info, status):
            if status:
                log.debug("sd status: %r", status)
            with buf_lock:
                buf_chunks.append(indata.copy().flatten())

        def record_loop():
            try:
                import sounddevice as sd2
                stream = sd2.InputStream(
                    samplerate=MIC_SAMPLE_RATE,
                    channels=1,
                    dtype="float32",
                    callback=cb,
                )
                stream.start()
                time.sleep(total_sec)
                stream.stop()
                stream.close()
            except Exception as e:  # noqa: BLE001
                err_slot["e"] = repr(e)
            finally:
                done_event.set()

        threading.Thread(target=record_loop, daemon=True).start()

        last_emit = ""
        started = time.perf_counter()
        while True:
            await asyncio.sleep(chunk_sec)
            if "e" in err_slot:
                yield _sse({"event": "error", "message": err_slot["e"]})
                return
            with buf_lock:
                if not buf_chunks:
                    continue
                audio = np.concatenate(buf_chunks).copy()
            # Transcribe off the event loop so the generator stays responsive
            try:
                partial, _ = await asyncio.to_thread(voice.transcribe_array, audio)
            except Exception as e:  # noqa: BLE001
                log.warning("partial transcribe failed: %r", e)
                partial = last_emit
            if partial and partial != last_emit:
                yield _sse({"event": "partial", "text": partial})
                last_emit = partial
            if done_event.is_set() and (time.perf_counter() - started) >= total_sec:
                break

        # Final pass, transcribe the whole buffer once more for stability
        with buf_lock:
            if not buf_chunks:
                yield _sse({"event": "final", "text": "", "asr_ms": 0})
                return
            audio = np.concatenate(buf_chunks)
        # Save for downstream pipeline use (not returned, but kept in /tmp)
        wav_out = _Path(_tempfile.mktemp(suffix=".wav"))
        import soundfile as sf2
        sf2.write(str(wav_out), audio, MIC_SAMPLE_RATE)
        try:
            final_text, asr_ms = await asyncio.to_thread(voice.transcribe_array, audio)
        except Exception as e:  # noqa: BLE001
            yield _sse({"event": "error", "message": f"final transcribe failed: {e!r}"})
            return
        yield _sse({"event": "final", "text": final_text, "asr_ms": round(asr_ms, 1)})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.post("/api/voice/live")
async def voice_live(req: LiveVoiceRequest) -> dict[str, Any]:
    """Record `seconds` directly from the system mic via sounddevice, then
    transcribe + answer + synthesize. Avoids WKWebView's getUserMedia gate.

    The recording itself is sync, Python sounddevice blocks for the duration.
    That's fine: the Tauri front-end shows a "recording…" UI for that interval.
    """
    import base64
    import time as _time
    from revvec.voice.stt_tts import get_voice_agent

    voice = get_voice_agent()
    timings: dict[str, float] = {}

    # 1) record
    t0 = _time.perf_counter()
    wav_in = voice.record(seconds=req.seconds)
    timings["record"] = (_time.perf_counter() - t0) * 1000

    # 2) transcribe
    transcript, asr_ms = voice.transcribe(wav_in)
    timings["asr"] = asr_ms
    if not transcript:
        return {"transcript": "", "error": "empty transcription", "timings_ms": timings}

    # 3) retrieve + answer via the unified query pipeline
    q = QueryRequest(query_text=transcript, persona=req.persona)
    qresp = await query_endpoint(q)
    timings.update(qresp["timings_ms"])

    # 4) TTS
    t0 = _time.perf_counter()
    wav_out, tts_ms = voice.speak(qresp["answer"])
    timings["tts"] = tts_ms
    audio_b64 = base64.b64encode(wav_out.read_bytes()).decode()

    return {
        **qresp,
        "transcript": transcript,
        "answer_audio_b64": audio_b64,
        "timings_ms": timings,
    }


# ─── /api/query/stream, SSE token stream ──────────────────────────────────


def _sse(event: dict[str, Any]) -> bytes:
    """Pack one SSE message."""
    import json as _json
    return f"data: {_json.dumps(event, ensure_ascii=False)}\n\n".encode("utf-8")


@app.post("/api/query/stream")
async def query_stream(req: QueryRequest) -> StreamingResponse:
    """Same contract as /api/query but streams the LLM's tokens as SSE.

    Event types:
      - start : { persona, retrieved, top_score, from_cache, general_mode }
      - delta : { text }           (repeated)
      - done  : { answer, citations, timings_ms, retrieved, from_cache, general_mode }
    """
    import asyncio

    async def gen():
        import json as _json
        timings: dict[str, float] = {}
        t_total = time.perf_counter()
        c = _ensure_client()
        embedder = get_embedder()

        # cache lookup, skip when we have history or a user_profile.
        has_history = bool(req.history)
        profile = _profile_dict(req.user_profile)
        has_profile = profile is not None
        q_emb = embedder.embed_text(req.query_text)[0].tolist()
        t0 = time.perf_counter()
        cached = (
            state.cache.lookup(q_emb, req.persona)
            if (req.use_cache and not has_history and not has_profile)
            else None
        )
        timings["cache_lookup"] = (time.perf_counter() - t0) * 1000

        if cached:
            cites_raw = cached.get("citations_json") or "[]"
            try:
                cites = _json.loads(cites_raw)
            except Exception:  # noqa: BLE001
                cites = []
            timings["total"] = (time.perf_counter() - t_total) * 1000
            actian = _actian_block(
                path="cache",
                vectors=["text_vec"],
                actian_ms=timings["cache_lookup"],
                summary="answer cache hit · cosine ≥ 0.95",
                operation="points.search(using=text_vec, score_threshold=0.95, filter=entity_type=answer_cache)",
            )
            yield _sse({
                "event": "start", "persona": req.persona,
                "from_cache": True, "general_mode": False,
                "retrieved": 0, "top_score": None,
                "actian": actian,
            })
            yield _sse({"event": "delta", "text": cached["answer"]})
            yield _sse({
                "event": "done",
                "answer": cached["answer"],
                "citations": cites,
                "from_cache": True, "general_mode": False,
                "retrieved": 0, "top_score": None,
                "timings_ms": timings,
                "actian": actian,
            })
            state.audit.record({
                "action": "query", "persona": req.persona,
                "query": req.query_text[:500], "from_cache": True,
                "general_mode": False, "citation_count": len(cites),
                "total_ms": round(timings["total"], 1), "streamed": True,
            })
            return

        # retrieve
        t0 = time.perf_counter()
        hits = state.retrieval.retrieve(query_text=req.query_text, persona=req.persona, limit=req.limit)
        timings["retrieve"] = (time.perf_counter() - t0) * 1000

        top_score = hits[0].score_semantic if hits else 0.0
        weak = _is_greeting(req.query_text) or (not hits) or (top_score < GENERAL_FALLBACK_THRESHOLD)
        llm = _ensure_llm()

        actian = _actian_block(
            path="general" if weak else "search",
            vectors=["text_vec"],
            actian_ms=timings.get("retrieve", 0.0),
            hits_used=len(hits),
            top_score=round(top_score, 4) if hits else None,
            summary=(
                "no strong match · model knowledge fallback"
                if weak else
                f"single-vector search · {len(hits)} chunks · BM25 rerank"
            ),
            operation=(
                "points.search(using=text_vec, limit=200) → top score below threshold"
                if weak else
                "points.search(using=text_vec, limit=200) → stage 2: Okapi BM25 (industrial-code-aware tokenizer), 0.7·cosine + 0.3·BM25"
            ),
        )
        yield _sse({
            "event": "start", "persona": req.persona,
            "from_cache": False, "general_mode": weak,
            "retrieved": len(hits), "top_score": round(top_score, 4),
            "actian": actian,
        })

        t0 = time.perf_counter()
        history_dicts = [h.model_dump() for h in (req.history or [])]
        stream = (
            llm.stream_generate_general(
                req.persona, req.query_text,
                max_tokens=2048, history=history_dicts, user_profile=profile,
            )
            if weak else
            llm.stream_generate_grounded(
                req.persona, req.query_text, hits,
                max_tokens=2048, history=history_dicts, user_profile=profile,
            )
        )
        final_answer = ""
        final_citations: list = []
        for delta, is_done, full, cites in stream:
            if is_done:
                final_answer = full
                final_citations = cites
                break
            yield _sse({"event": "delta", "text": delta})
            await asyncio.sleep(0)  # give the event loop a chance to flush

        timings["generate"] = (time.perf_counter() - t0) * 1000
        timings["total"] = (time.perf_counter() - t_total) * 1000

        citations_out = [
            {"index": c.index, "entity_id": c.entity_id, "title": c.title, "preview": c.preview}
            for c in final_citations
        ]

        yield _sse({
            "event": "done",
            "answer": final_answer,
            "citations": citations_out,
            "from_cache": False, "general_mode": weak,
            "retrieved": len(hits), "top_score": round(top_score, 4),
            "timings_ms": timings,
            "actian": actian,
        })

        # cache + audit, skip cache write for multi-turn or when a user
        # profile is set (the answer was tailored to this user).
        if not weak and final_answer and not has_history and not has_profile:
            try:
                state.cache.write(q_emb, req.persona, req.query_text, final_answer, final_citations)
            except Exception as e:  # noqa: BLE001
                log.warning("cache write failed: %r", e)
        state.audit.record({
            "action": "query", "persona": req.persona,
            "query": req.query_text[:500],
            "retrieved": len(hits), "top_score": round(top_score, 4),
            "from_cache": False, "general_mode": weak,
            "citation_count": len(citations_out),
            "total_ms": round(timings["total"], 1), "streamed": True,
        })

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ─── /api/admin/*, audit + compliance endpoints ────────────────────────────


class ForgetRequest(BaseModel):
    entity_id: str
    operator: str = "anonymous"
    reason: str = ""


@app.get("/api/admin/audit")
async def admin_audit(day: str | None = None) -> dict[str, Any]:
    """Return today's (or given UTC day's) audit rows + chain verification."""
    rows = state.audit.read_rows(day)
    p = state.audit.log_path_for(day)
    ok, n_checked, err = state.audit.verify(p)
    return {
        "day": day or p.stem,
        "rows": rows,
        "chain_ok": ok,
        "rows_checked": n_checked,
        "error": err,
    }


@app.post("/api/admin/snapshot")
async def admin_snapshot() -> dict[str, Any]:
    """Trigger an on-demand VDE snapshot + record the attempt in the audit log.

    NOTE: Actian VectorAI DB v1.0 beta returns UNIMPLEMENTED for `save_snapshot`.
    We record the attempt in the audit log either way, so the intent + timestamp
    is preserved for regulatory review even when the server-side RPC is pending.
    """
    c = _ensure_client()
    try:
        ok = bool(c.vde.save_snapshot(config.COLLECTION))
        err = None
    except Exception as e:  # noqa: BLE001
        ok = False
        err = repr(e)[:240]
        log.info("save_snapshot fell through: %s", err)

    state.audit.record({
        "action": "snapshot",
        "ok": ok,
        "collection": config.COLLECTION,
        "server_unimplemented": (not ok and "Unimplemented" in (err or "")),
        "error": err,
    })
    return {
        "ok": ok,
        "collection": config.COLLECTION,
        "note": (
            "Actian server returned UNIMPLEMENTED for save_snapshot. "
            "Audit row was still written."
            if not ok and "Unimplemented" in (err or "") else None
        ),
    }


@app.post("/api/admin/forget")
async def admin_forget(req: ForgetRequest) -> dict[str, Any]:
    """Forget an entity: pre-snapshot, cascade-delete, then audit-log."""
    c = _ensure_client()
    # Pre-snapshot, so we can prove what was erased
    snap_ok = False
    try:
        snap_ok = bool(c.vde.save_snapshot(config.COLLECTION))
    except Exception as e:  # noqa: BLE001
        log.warning("pre-forget snapshot failed: %r", e)

    f = FilterBuilder().must(Field("entity_id").eq(req.entity_id)).build()
    try:
        before = c.points.count(config.COLLECTION, filter=f)
    except Exception:  # noqa: BLE001
        before = -1  # count may fail on filter-index edge cases
    try:
        c.points.delete(config.COLLECTION, filter=f)
        ok = True
    except Exception as e:  # noqa: BLE001
        ok = False
        err = repr(e)[:200]
        state.audit.record({
            "action": "forget",
            "entity_id": req.entity_id,
            "operator": req.operator,
            "reason": req.reason[:200],
            "pre_snapshot_ok": snap_ok,
            "deleted_count": 0,
            "ok": False,
            "error": err,
        })
        raise HTTPException(status_code=500, detail=f"delete failed: {e!r}") from e

    state.audit.record({
        "action": "forget",
        "entity_id": req.entity_id,
        "operator": req.operator,
        "reason": req.reason[:200],
        "pre_snapshot_ok": snap_ok,
        "deleted_count": before,
        "ok": ok,
    })
    return {"ok": ok, "deleted_count": before, "pre_snapshot_ok": snap_ok}


@app.post("/api/admin/cache/clear")
async def admin_cache_clear() -> dict[str, Any]:
    """Delete every answer_cache point so subsequent queries hit fresh LLM
    generation. Also writes an audit row capturing the operator action."""
    c = _ensure_client()
    f = FilterBuilder().must(Field("entity_type").eq("answer_cache")).build()
    try:
        before = c.points.count(config.COLLECTION, filter=f)
    except Exception:  # noqa: BLE001
        before = -1
    try:
        c.points.delete(config.COLLECTION, filter=f)
        ok = True
        err = None
    except Exception as e:  # noqa: BLE001
        ok = False
        err = repr(e)[:200]
    state.audit.record({
        "action": "cache_clear",
        "deleted_count": before,
        "ok": ok,
        "error": err,
    })
    return {"ok": ok, "deleted_count": before, "error": err}


# ─── entry ──────────────────────────────────────────────────────────────────


def main() -> None:
    import uvicorn
    host = "127.0.0.1"
    port = 8000
    if "--port" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1])
    log.info("revvec server starting on %s:%d", host, port)
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
