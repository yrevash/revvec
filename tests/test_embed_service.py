"""Phase 1 — EmbedAgent tests.

Text path exercises a REAL Qwen3-Embedding-0.6B load (requires model to be
downloaded; triggers a HuggingFace snapshot pull on first run).

The other paths are asserted NotImplementedError here; they'll become real as
the relevant ingestor lands.
"""
from __future__ import annotations

import numpy as np
import pytest

from revvec import config
from revvec.embed.service import EmbedAgent, get_embedder


def test_embedder_is_singleton():
    a = EmbedAgent()
    b = EmbedAgent()
    assert a is b
    assert get_embedder() is a


@pytest.mark.slow
def test_embed_text_single():
    emb = get_embedder()
    vec = emb.embed_text("Perseverance rover MEDA atmospheric pressure sensor")
    assert isinstance(vec, np.ndarray)
    assert vec.shape == (1, config.DIM_TEXT)
    # Sanity: embeddings aren't all-zero or constant
    assert float(np.abs(vec).max()) > 0.0


@pytest.mark.slow
def test_embed_text_batch():
    emb = get_embedder()
    vecs = emb.embed_text([
        "Perseverance rover landed in Jezero crater on sol 0.",
        "MEDA records pressure, temperature, wind, and dust opacity.",
        "CDRA removes CO2 from ISS atmosphere.",
    ])
    assert vecs.shape == (3, config.DIM_TEXT)

    # Semantic check: the two Mars-related strings should be closer than to the ISS one.
    def cos(a, b):
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
    d_mars = cos(vecs[0], vecs[1])
    d_iss = cos(vecs[0], vecs[2])
    assert d_mars > d_iss, f"expected Mars-Mars closer than Mars-ISS, got {d_mars} vs {d_iss}"


# page_vec slot is declared in schema but unused — Nomic Embed Multimodal 3B
# can't be loaded by transformers AutoModel. SopIngestor populates pages into
# text_vec + photo_vec instead. No test needed for a dead path.
