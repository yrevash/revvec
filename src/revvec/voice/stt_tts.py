"""VoiceAgent, Whisper-large-v3-turbo (MLX) for ASR + Kokoro-82M for TTS.

Design goals:
  - CPU-friendly TTS (Kokoro is ~300 MB, Apache-2.0, MOS 4.2 on TTS Arena)
  - Apple Silicon native ASR via MLX (~5× faster than whisper-large-v3)
  - One method per job: transcribe(wav) → str, speak(text) → wav, record(sec) → wav

No streaming yet, Phase 5 covers batch calls. Phase 6 adds WebSocket streaming
when the UI lands.
"""
from __future__ import annotations

import logging
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

import numpy as np

from revvec import config

log = logging.getLogger(__name__)


TTS_SAMPLE_RATE = 24000  # Kokoro default
MIC_SAMPLE_RATE = 16000  # Whisper prefers 16k


class VoiceAgent:
    """Thread-safe singleton for the voice stack."""

    _instance: "VoiceAgent | None" = None
    _ctor_lock = threading.Lock()

    def __new__(cls) -> "VoiceAgent":
        if cls._instance is None:
            with cls._ctor_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init_once()
        return cls._instance

    def _init_once(self) -> None:
        self._tts_pipeline: Any = None
        self._tts_lock = threading.Lock()
        # mlx_whisper is stateless; no explicit load needed

    # ─── ASR ─────────────────────────────────────────────────────────────────

    def transcribe(self, wav_path: str | Path, *, language: str = "en") -> tuple[str, float]:
        """Transcribe a WAV file via mlx-whisper. Returns (text, elapsed_ms)."""
        import mlx_whisper
        t0 = time.perf_counter()
        result = mlx_whisper.transcribe(
            str(wav_path),
            path_or_hf_repo=config.ASR_MODEL,
            language=language,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000
        text = (result.get("text") or "").strip()
        log.info("asr: %.0f ms → %r", elapsed_ms, text[:80])
        return text, elapsed_ms

    def transcribe_array(self, audio: np.ndarray, *, language: str = "en") -> tuple[str, float]:
        """Transcribe a mono float32 numpy array (16 kHz). Used for live streaming
        so we don't round-trip through the filesystem for every partial."""
        import mlx_whisper
        t0 = time.perf_counter()
        # mlx_whisper accepts numpy arrays directly
        result = mlx_whisper.transcribe(
            audio.astype(np.float32),
            path_or_hf_repo=config.ASR_MODEL,
            language=language,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000
        text = (result.get("text") or "").strip()
        return text, elapsed_ms

    # ─── TTS ─────────────────────────────────────────────────────────────────

    def _load_tts(self) -> Any:
        if self._tts_pipeline is not None:
            return self._tts_pipeline
        with self._tts_lock:
            if self._tts_pipeline is not None:
                return self._tts_pipeline
            from kokoro import KPipeline
            log.info("Loading TTS model: %s", config.TTS_MODEL)
            # 'a' = American English; Kokoro auto-downloads weights on first use
            self._tts_pipeline = KPipeline(lang_code="a")
            log.info("TTS model loaded")
        return self._tts_pipeline

    def speak(
        self,
        text: str,
        out_path: str | Path | None = None,
        *,
        voice: str | None = None,
    ) -> tuple[Path, float]:
        """Synthesize `text` to a WAV file. Returns (path, elapsed_ms)."""
        import soundfile as sf

        pipeline = self._load_tts()
        voice_id = voice or config.TTS_VOICE
        out = Path(out_path) if out_path else Path(tempfile.mktemp(suffix=".wav"))

        t0 = time.perf_counter()
        audios: list[np.ndarray] = []
        for _, _, audio in pipeline(text, voice=voice_id):
            audios.append(audio)
        if not audios:
            raise RuntimeError("TTS produced no audio")
        full = np.concatenate(audios)
        sf.write(str(out), full, TTS_SAMPLE_RATE)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        log.info("tts: %.0f ms → %s (%d samples, %.1fs)",
                 elapsed_ms, out.name, len(full), len(full) / TTS_SAMPLE_RATE)
        return out, elapsed_ms

    # ─── Mic recording ───────────────────────────────────────────────────────

    def record(self, seconds: float = 5.0, out_path: str | Path | None = None) -> Path:
        """Capture `seconds` from the default input device at 16 kHz mono.

        On macOS, first call will prompt for microphone permission.
        """
        import sounddevice as sd
        import soundfile as sf

        out = Path(out_path) if out_path else Path(tempfile.mktemp(suffix=".wav"))
        n_samples = int(seconds * MIC_SAMPLE_RATE)
        log.info("recording %.1fs from mic...", seconds)
        audio = sd.rec(
            n_samples,
            samplerate=MIC_SAMPLE_RATE,
            channels=1,
            dtype="float32",
        )
        sd.wait()
        sf.write(str(out), audio, MIC_SAMPLE_RATE)
        log.info("recorded → %s", out.name)
        return out

    # ─── Playback (convenience) ──────────────────────────────────────────────

    @staticmethod
    def play(wav_path: str | Path, blocking: bool = True) -> None:
        import sounddevice as sd
        import soundfile as sf
        data, sr = sf.read(str(wav_path))
        sd.play(data, sr)
        if blocking:
            sd.wait()


def get_voice_agent() -> VoiceAgent:
    return VoiceAgent()
