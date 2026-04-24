"""Phase 0 — offline schema tests (don't require Actian server).

Post-April-2026 SOTA review: dims upgraded; voice transcripts fold into
text_vec with payload modality="voice" (no separate transcript_vec).
"""
from __future__ import annotations

from revvec import config
from revvec.memory.schema import build_vectors_config


def test_schema_has_three_named_vectors():
    vc = build_vectors_config()
    assert set(vc.keys()) == set(config.VECTOR_NAMES)
    assert set(vc.keys()) == {"text_vec", "photo_vec", "sensor_vec"}


def test_schema_dimensions_pinned():
    vc = build_vectors_config()
    assert vc["text_vec"].size == config.DIM_TEXT == 1024   # Qwen3-Embedding-0.6B
    assert vc["photo_vec"].size == config.DIM_PHOTO == 1024  # DINOv2 ViT-L
    assert vc["sensor_vec"].size == config.DIM_SENSOR == 512  # Chronos-Bolt-small pooled


def test_config_defaults():
    assert config.COLLECTION == "revvec_memory"
    assert config.VECTOR_NAMES == ("text_vec", "photo_vec", "sensor_vec")


def test_model_ids_reference_current_picks():
    # Post-review picks, with two hackathon-scope swaps documented:
    #  - DINOv3 is gated on HF → fell back to DINOv2-L (same 1024d, ungated)
    #  - Nomic Embed Multimodal 3B has a custom config AutoModel can't load →
    #    SopIngestor uses page-as-image (DINOv2) + text extraction (Qwen3)
    assert config.TEXT_EMBED_MODEL == "Qwen/Qwen3-Embedding-0.6B"
    assert config.PHOTO_EMBED_MODEL == "facebook/dinov2-large"
    assert config.LLM_MODEL == "mlx-community/Qwen3-8B-4bit"
    assert config.ASR_MODEL == "nvidia/parakeet-tdt-0.6b-v2"
    assert config.TTS_MODEL == "hexgrad/Kokoro-82M"
