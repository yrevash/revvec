"""LLMAgent — Qwen3-4B-Instruct-2507-4bit via MLX.

Apple Silicon native, ~3.5 GB active, ~60-90 tok/s on M3. The -Instruct-2507
refresh (Aug 2025) gives us the highest IFEval score of any mlx-community
model under 6 GB — critical for honoring the "[source:N]" citation format.

Grounded generation ONLY — system prompt forbids fabrication and requires
citations.
"""
from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from revvec import config

log = logging.getLogger(__name__)


PROMPT_DIR = Path(__file__).resolve().parent / "prompts"


@dataclass
class Citation:
    index: int              # the [source:N] number the model wrote
    entity_id: str
    title: str
    preview: str


@dataclass
class GenerationResult:
    answer: str
    citations: list[Citation] = field(default_factory=list)
    total_ms: float = 0.0
    from_cache: bool = False
    persona: str = ""
    raw_prompt_tokens: int = 0

    @property
    def has_fabricated_citations(self) -> bool:
        """Did the model cite an index that didn't exist in the context?"""
        return any(c.entity_id == "" for c in self.citations)


class LLMAgent:
    _instance: "LLMAgent | None" = None
    _lock = threading.Lock()

    def __new__(cls) -> "LLMAgent":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init_once()
        return cls._instance

    def _init_once(self) -> None:
        self._model = None
        self._tok = None
        self._model_name = config.LLM_MODEL
        self._model_lock = threading.Lock()

    # ─── model loading ───────────────────────────────────────────────────────

    def _load(self) -> tuple[Any, Any]:
        if self._model is not None:
            return self._model, self._tok
        with self._model_lock:
            if self._model is not None:
                return self._model, self._tok
            from mlx_lm import load
            log.info("Loading LLM: %s", self._model_name)
            self._model, self._tok = load(self._model_name)
            log.info("LLM loaded")
        return self._model, self._tok

    # ─── prompt assembly ─────────────────────────────────────────────────────

    @staticmethod
    def _load_prompt_file(name: str) -> str:
        p = PROMPT_DIR / f"{name}.txt"
        return p.read_text() if p.exists() else ""

    @classmethod
    def build_system_prompt(cls, persona: str) -> str:
        base = cls._load_prompt_file("base")
        overlay = cls._load_prompt_file(persona) if persona else ""
        if overlay:
            return f"{base}\n\n{overlay}"
        return base

    @staticmethod
    def _apply_user_profile(system: str, profile: dict[str, str] | None) -> str:
        """Append a USER CONTEXT block to the system prompt.

        Only fields with a non-empty string value are included. Returns the
        original system prompt unchanged if the profile is empty or missing.
        """
        if not profile:
            return system
        rows: list[str] = []
        for k in ("role", "experience", "focus", "preferences", "notes"):
            v = profile.get(k)
            if isinstance(v, str) and v.strip():
                rows.append(f"- {k}: {v.strip()}")
        if not rows:
            return system
        return (
            system
            + "\n\nUSER CONTEXT (the user told us about themselves):\n"
            + "\n".join(rows)
            + "\n\nWhen relevant, tailor the answer to this user's role and "
            "background. Do not invent details not in the local sources, but "
            "emphasize parts of the answer most useful to them."
        )

    @staticmethod
    def _history_messages(
        history: Sequence[dict[str, str]] | None,
        *,
        max_turns: int = 6,
        max_chars: int = 4000,
    ) -> list[dict[str, str]]:
        """Build chat-template message dicts from a prior-turns list, budgeted
        newest-first by character count so recent context survives truncation."""
        if not history:
            return []
        cleaned = [
            {"role": h.get("role"), "content": (h.get("content") or "").strip()}
            for h in history
            if h.get("role") in ("user", "assistant") and (h.get("content") or "").strip()
        ]
        tail = cleaned[-max_turns:]
        budgeted: list[dict[str, str]] = []
        used = 0
        for m in reversed(tail):
            if used + len(m["content"]) > max_chars:
                break
            budgeted.append(m)
            used += len(m["content"])
        budgeted.reverse()
        return budgeted

    @staticmethod
    def format_context(chunks: Sequence[Any]) -> tuple[str, list[tuple[int, str, str, str]]]:
        """Return (formatted_block, index_map).

        index_map: list of (N, entity_id, title, preview) tuples for citation resolution.
        """
        lines: list[str] = []
        index_map: list[tuple[int, str, str, str]] = []
        for i, h in enumerate(chunks, 1):
            entity_id = str(getattr(h, "id", "")) or str(h.payload.get("entity_id", ""))
            title = str(h.payload.get("title", "") or "")
            # Use the full stored preview (typically 512 chars from ingestion)
            # and clean up common PDF artifacts that confuse the LLM.
            raw = str(h.payload.get("text_preview", "") or "")
            # collapse orphan line numbers and repeated newlines
            import re as _re
            cleaned = _re.sub(r"\n\s*\d{1,4}\s*\n", "\n", raw)  # kill lone page/line numbers
            cleaned = _re.sub(r"\n+", " ", cleaned).strip()
            index_map.append((i, entity_id, title, cleaned))
            lines.append(f"[{i}] {title}")
            lines.append(f"    {cleaned}")
        return "\n\n".join(lines), index_map

    # ─── main entry ──────────────────────────────────────────────────────────

    def generate(
        self,
        persona: str,
        question: str,
        chunks: Sequence[Any],
        *,
        max_tokens: int = 160,
        temperature: float = 0.0,
        history: Sequence[dict[str, str]] | None = None,
        user_profile: dict[str, str] | None = None,
    ) -> GenerationResult:
        from mlx_lm import generate as mlx_generate

        if not chunks:
            return GenerationResult(
                answer="Not found in the provided sources.",
                citations=[],
                total_ms=0.0,
                persona=persona,
            )

        model, tok = self._load()
        system_prompt = self._apply_user_profile(
            self.build_system_prompt(persona), user_profile
        )
        context_block, index_map = self.format_context(chunks)
        user_prompt = f"CONTEXT:\n{context_block}\n\nQUESTION: {question}"

        messages = [
            {"role": "system", "content": system_prompt},
            *self._history_messages(history),
            {"role": "user",   "content": user_prompt},
        ]
        prompt = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)

        t0 = time.perf_counter()
        # mlx-lm 0.31 does not accept a `temperature` kwarg on the top-level
        # generate(); greedy by default, which is fine for grounded citations.
        answer = mlx_generate(model, tok, prompt=prompt, max_tokens=max_tokens)
        total_ms = (time.perf_counter() - t0) * 1000

        citations = self._extract_citations(answer, index_map)

        return GenerationResult(
            answer=answer.strip(),
            citations=citations,
            total_ms=total_ms,
            persona=persona,
        )

    # ─── streaming generation ────────────────────────────────────────────────

    def stream_generate_grounded(
        self,
        persona: str,
        question: str,
        chunks: Sequence[Any],
        *,
        max_tokens: int = 160,
        history: Sequence[dict[str, str]] | None = None,
        user_profile: dict[str, str] | None = None,
    ):
        """Yield `(delta_text, is_done, full_text, citations)` tuples.

        On each token: (delta, False, accumulated, []).
        On completion: ("", True, full_answer, resolved_citations).
        Callers must run this on the main event loop thread because MLX's
        GPU stream is thread-local.
        """
        from mlx_lm import stream_generate as mlx_stream_generate

        if not chunks:
            yield ("Not found in the provided sources.", False,
                   "Not found in the provided sources.", [])
            yield ("", True, "Not found in the provided sources.", [])
            return

        model, tok = self._load()
        system = self._apply_user_profile(
            self.build_system_prompt(persona), user_profile
        )
        context_block, index_map = self.format_context(chunks)
        user_prompt = f"CONTEXT:\n{context_block}\n\nQUESTION: {question}"
        messages = [
            {"role": "system", "content": system},
            *self._history_messages(history),
            {"role": "user",   "content": user_prompt},
        ]
        prompt = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)

        full = ""
        for response in mlx_stream_generate(model, tok, prompt=prompt, max_tokens=max_tokens):
            delta = getattr(response, "text", "") or ""
            if not delta:
                continue
            full += delta
            yield (delta, False, full, [])

        citations = self._extract_citations(full, index_map)
        yield ("", True, full.strip(), citations)

    def stream_generate_general(
        self,
        persona: str,
        question: str,
        *,
        max_tokens: int = 140,
        history: Sequence[dict[str, str]] | None = None,
        user_profile: dict[str, str] | None = None,
    ):
        """Streaming variant of generate_general — same delta/done contract."""
        from mlx_lm import stream_generate as mlx_stream_generate

        model, tok = self._load()
        system = self._apply_user_profile(
            "You are revvec, an on-device industrial assistant. The local knowledge base "
            "did not contain information relevant to the user's question, so answer briefly "
            "from general knowledge. Begin your reply with '(from model knowledge)' so the "
            "user knows it isn't grounded in their documents. Be concise — 1–2 sentences — "
            "and if the question seems like small talk, greet the user and list a few kinds "
            "of questions revvec CAN answer (e.g., Perseverance MEDA, Mars 2020 EDL, Apollo "
            "anomalies, CMAPSS engine prognostics).",
            user_profile,
        )
        messages = [
            {"role": "system", "content": system},
            *self._history_messages(history),
            {"role": "user",   "content": question},
        ]
        prompt = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)

        full = ""
        for response in mlx_stream_generate(model, tok, prompt=prompt, max_tokens=max_tokens):
            delta = getattr(response, "text", "") or ""
            if not delta:
                continue
            full += delta
            yield (delta, False, full, [])
        yield ("", True, full.strip(), [])

    # ─── general (no-context) generation ─────────────────────────────────────

    def generate_general(
        self,
        persona: str,
        question: str,
        *,
        max_tokens: int = 160,
        history: Sequence[dict[str, str]] | None = None,
        user_profile: dict[str, str] | None = None,
    ) -> GenerationResult:
        """Answer conversationally when retrieval finds nothing useful.

        Explicitly signals to the user that this answer is from model knowledge
        rather than their local corpus.
        """
        from mlx_lm import generate as mlx_generate

        model, tok = self._load()
        system = self._apply_user_profile(
            "You are revvec, an on-device industrial assistant. The local knowledge base "
            "did not contain information relevant to the user's question, so answer briefly "
            "from general knowledge. Begin your reply with '(from model knowledge)' so the "
            "user knows it isn't grounded in their documents. Be concise — 1–2 sentences — "
            "and if the question seems like small talk, greet the user and list a few kinds "
            "of questions revvec CAN answer (e.g., Perseverance MEDA, Mars 2020 EDL, Apollo "
            "anomalies, CMAPSS engine prognostics).",
            user_profile,
        )
        messages = [
            {"role": "system", "content": system},
            *self._history_messages(history),
            {"role": "user",   "content": question},
        ]
        prompt = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        t0 = time.perf_counter()
        answer = mlx_generate(model, tok, prompt=prompt, max_tokens=max_tokens)
        total_ms = (time.perf_counter() - t0) * 1000
        return GenerationResult(
            answer=answer.strip(),
            citations=[],
            total_ms=total_ms,
            persona=persona,
        )

    # ─── citation extraction ────────────────────────────────────────────────

    _CITE_RE = re.compile(r"\[source:\s*(\d+)\s*\]")

    @classmethod
    def _extract_citations(
        cls,
        answer: str,
        index_map: list[tuple[int, str, str, str]],
    ) -> list[Citation]:
        """Parse [source:N] markers in the answer, resolve to entity_ids.

        A cite whose index is out of range (model fabricated a number) is still
        returned but with entity_id="" so callers can detect it.
        """
        idx_lookup = {n: (eid, title, prev) for (n, eid, title, prev) in index_map}
        citations: list[Citation] = []
        seen: set[int] = set()
        for m in cls._CITE_RE.finditer(answer):
            n = int(m.group(1))
            if n in seen:
                continue
            seen.add(n)
            if n in idx_lookup:
                eid, title, prev = idx_lookup[n]
                citations.append(Citation(index=n, entity_id=eid, title=title, preview=prev))
            else:
                citations.append(Citation(index=n, entity_id="", title="", preview=""))
        return citations
