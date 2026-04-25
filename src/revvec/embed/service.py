"""EmbedAgent, unified multi-model embedding service.

Every sub-ingestor calls in here; nobody else instantiates an embedding model.
Models are lazy-loaded singletons with an optional TTL-unload (added in Phase 8
if the 16 GB RAM budget pushes back).

Slots:
  text_vec (1024d)  , Qwen/Qwen3-Embedding-0.6B (MRL)
  page_vec (3584d)  , nomic-ai/nomic-embed-multimodal-3b  (Phase 1 later)
  photo_vec (1024d) , facebook/dinov3-vitl16-pretrain-lvd1689m  (Phase 1 later)
  sensor_vec (512d) , amazon/chronos-2  (Phase 1 later / Phase 2)
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Sequence

import numpy as np

from revvec import config

log = logging.getLogger(__name__)


class EmbedAgent:
    """Thread-safe singleton holder for every embedding model revvec uses."""

    _instance: "EmbedAgent | None" = None
    _instance_lock = threading.Lock()

    def __new__(cls) -> "EmbedAgent":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init_once()
        return cls._instance

    def _init_once(self) -> None:
        self._text_model: Any = None
        self._photo_model: Any = None
        self._page_model: Any = None
        self._sensor_model: Any = None
        self._text_lock = threading.Lock()
        self._photo_lock = threading.Lock()
        self._page_lock = threading.Lock()
        self._sensor_lock = threading.Lock()

    # ─── text ────────────────────────────────────────────────────────────────

    def _load_text(self) -> Any:
        if self._text_model is not None:
            return self._text_model
        with self._text_lock:
            if self._text_model is not None:
                return self._text_model
            from sentence_transformers import SentenceTransformer
            log.info("Loading text embed model: %s", config.TEXT_EMBED_MODEL)
            self._text_model = SentenceTransformer(config.TEXT_EMBED_MODEL)
            log.info("Text embed model loaded")
        return self._text_model

    def embed_text(self, texts: str | Sequence[str]) -> np.ndarray:
        """Embed one string or a batch. Returns shape (N, DIM_TEXT)."""
        model = self._load_text()
        if isinstance(texts, str):
            texts = [texts]
        embs = model.encode(list(texts), show_progress_bar=False, convert_to_numpy=True)
        if embs.shape[-1] != config.DIM_TEXT:
            raise AssertionError(
                f"text embed dim mismatch: got {embs.shape[-1]}, expected {config.DIM_TEXT}"
            )
        return embs

    # ─── photo (DINOv3 ViT-L) ────────────────────────────────────────────────

    def _load_photo(self) -> tuple[Any, Any]:
        """Return (processor, model); lazy-load DINOv3 on first call."""
        if self._photo_model is not None:
            return self._photo_model
        with self._photo_lock:
            if self._photo_model is not None:
                return self._photo_model
            from transformers import AutoImageProcessor, AutoModel
            import torch
            log.info("Loading photo embed model: %s", config.PHOTO_EMBED_MODEL)
            processor = AutoImageProcessor.from_pretrained(config.PHOTO_EMBED_MODEL)
            model = AutoModel.from_pretrained(config.PHOTO_EMBED_MODEL).eval()
            # Prefer Apple Silicon MPS if available, otherwise CPU
            device = "mps" if torch.backends.mps.is_available() else "cpu"
            model = model.to(device)
            self._photo_model = (processor, model, device, torch)
            log.info("Photo embed model loaded on %s", device)
        return self._photo_model

    def embed_photo(self, images: Sequence[Any] | Any) -> np.ndarray:
        """Embed one or more PIL.Image.Image into photo_vec (DIM_PHOTO=1024)."""
        processor, model, device, torch = self._load_photo()
        from PIL import Image as _Image
        if isinstance(images, _Image.Image):
            images = [images]
        images = [img.convert("RGB") for img in images]
        inputs = processor(images=images, return_tensors="pt").to(device)
        with torch.no_grad():
            outputs = model(**inputs)
        # DINOv3 outputs: prefer pooler_output; fall back to CLS token
        if getattr(outputs, "pooler_output", None) is not None:
            vecs = outputs.pooler_output
        else:
            vecs = outputs.last_hidden_state[:, 0, :]
        vecs = vecs.detach().cpu().numpy()
        if vecs.shape[-1] != config.DIM_PHOTO:
            raise AssertionError(
                f"photo embed dim mismatch: got {vecs.shape[-1]}, expected {config.DIM_PHOTO}"
            )
        return vecs

    # page_vec slot was removed from the schema (dead code trimmed)

    # ─── sensor (Chronos-Bolt-small) ─────────────────────────────────────────

    def _load_sensor(self) -> tuple[Any, str, Any]:
        if self._sensor_model is not None:
            return self._sensor_model
        with self._sensor_lock:
            if self._sensor_model is not None:
                return self._sensor_model
            import torch
            from chronos import BaseChronosPipeline
            log.info("Loading sensor embed model: %s", config.SENSOR_EMBED_MODEL)
            pipeline = BaseChronosPipeline.from_pretrained(
                config.SENSOR_EMBED_MODEL,
                torch_dtype=torch.float32,
                device_map="cpu",  # Chronos on MPS has kernel gaps; CPU is safe and fast enough for 512-step windows
            )
            self._sensor_model = (pipeline, "cpu", torch)
            log.info("Sensor embed model loaded on cpu")
        return self._sensor_model

    def embed_sensor(self, windows: Any) -> np.ndarray:
        """Embed 1D univariate time-series windows → sensor_vec (DIM_SENSOR=512).

        Accepts one of:
          - a 1D numpy array (single window)
          - a 2D numpy array shape (batch, length)
          - a list of 1D numpy arrays (variable-length windows OK)
        Mean-pools Chronos-Bolt encoder hidden states to a single fixed-dim vector.
        """
        pipeline, device, torch = self._load_sensor()

        if isinstance(windows, np.ndarray):
            if windows.ndim == 1:
                windows = [windows]
            elif windows.ndim == 2:
                windows = [w for w in windows]
            else:
                raise ValueError(f"sensor windows ndim must be 1 or 2, got {windows.ndim}")

        context = [torch.tensor(np.asarray(w), dtype=torch.float32) for w in windows]
        # Chronos-Bolt's `embed()` returns (encoder_hidden_states, scale_tensor).
        # encoder_hidden_states: (batch, seq_len, d_model)
        embeddings, _ = pipeline.embed(context)
        pooled = embeddings.mean(dim=1).detach().cpu().numpy()

        if pooled.shape[-1] != config.DIM_SENSOR:
            raise AssertionError(
                f"sensor embed dim mismatch: got {pooled.shape[-1]}, expected {config.DIM_SENSOR}"
            )
        return pooled

    # ─── lifecycle hooks (TTL unload comes later) ────────────────────────────

    def unload_text(self) -> None:
        self._text_model = None
        log.info("text embed model unloaded")

    def unload_all(self) -> None:
        self._text_model = None
        self._photo_model = None
        self._page_model = None
        self._sensor_model = None
        log.info("all embed models unloaded")


def get_embedder() -> EmbedAgent:
    """Module-level accessor used by ingestors/retrieval."""
    return EmbedAgent()
