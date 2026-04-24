"""Central configuration for revvec.

Loaded once at import time from environment + .env. Vector dimensions are pinned
here and referenced everywhere — do not change without a schema migration.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

REVVEC_DATA: Path = Path(os.environ.get("REVVEC_DATA", "./data")).resolve()
ACTIAN_URL: str = os.environ.get("ACTIAN_URL", "localhost:50052")
COLLECTION: str = os.environ.get("REVVEC_COLLECTION", "revvec_memory")

# Vector dimensions — pinned. Post-April-2026 SOTA review.
# Dropped page_vec: Actian's server-side set_payload crashes when a point has
# a declared named vector that's never populated. We'd never found a clean
# loader for Nomic Embed Multimodal 3B anyway, so the slot was dead weight.
# SopIngestor now puts PDF pages into text_vec + photo_vec (dual-vector,
# ColPali-intuition) per point.
DIM_TEXT = 1024         # Qwen3-Embedding-0.6B (MRL; can truncate to 256/512/768)
DIM_PHOTO = 1024        # DINOv2 ViT-L (ungated)
DIM_SENSOR = 512        # Chronos-Bolt-small (pooled encoder tokens)

VECTOR_NAMES: tuple[str, ...] = ("text_vec", "photo_vec", "sensor_vec")

# Embedder model IDs (Phase 1)
TEXT_EMBED_MODEL: str = os.environ.get("TEXT_EMBED_MODEL", "Qwen/Qwen3-Embedding-0.6B")
PHOTO_EMBED_MODEL: str = os.environ.get("PHOTO_EMBED_MODEL", "facebook/dinov2-large")  # DINOv3 is access-gated on HF; DINOv2-L is ungated and matches the 1024d slot
SENSOR_EMBED_MODEL: str = os.environ.get("SENSOR_EMBED_MODEL", "amazon/chronos-bolt-small")  # Chronos-2 needs custom loader; Chronos-Bolt-small has d_model=512 (matches DIM_SENSOR)
SENSOR_EMBED_MODEL_FALLBACK: str = os.environ.get("SENSOR_EMBED_MODEL_FALLBACK", "AutonLab/MOMENT-1-large")

# LLM (Phase 4) — Qwen3-8B via MLX (Apple Silicon native)
LLM_MODEL: str = os.environ.get("LLM_MODEL", "mlx-community/Qwen3-4B-Instruct-2507-4bit")  # 2.26 GB on disk, ~3.5 GB active; IFEval 83.4 / Arena-Hard 43.4 — tops mlx-community models under 6 GB active
OLLAMA_BASE_URL: str = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL: str = os.environ.get("OLLAMA_MODEL", "qwen3:8b-instruct")

# Voice (Phase 5) — Whisper-large-v3-turbo (MLX) + Kokoro TTS
# whisper-turbo is distilled large-v3: ~5× faster at nearly same quality; 809M params, ~1.5 GB active
ASR_MODEL: str = os.environ.get("ASR_MODEL", "mlx-community/whisper-large-v3-turbo")
TTS_MODEL: str = os.environ.get("TTS_MODEL", "hexgrad/Kokoro-82M")
TTS_VOICE: str = os.environ.get("TTS_VOICE", "af_heart")
