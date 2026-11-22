"""Local multilingual text embeddings (no API quota, queries never leave the server).

Model: intfloat/multilingual-e5-small (MIT licence, ~100 languages incl. all 11 app languages,
384 dimensions). E5 models expect "query: " / "passage: " prefixes.
Wang L, et al. Multilingual E5 Text Embeddings: A Technical Report. arXiv:2402.05672 (2024).
"""
from __future__ import annotations

import threading
from functools import lru_cache

import numpy as np

from app.config import get_settings

_lock = threading.Lock()


@lru_cache
def _model():
    from sentence_transformers import SentenceTransformer  # heavy import; load on first use

    with _lock:
        return SentenceTransformer(get_settings().embedding_model, device="cpu")


def _encode(texts: list[str], prefix: str) -> np.ndarray:
    v = _model().encode([prefix + t[:2000] for t in texts], normalize_embeddings=True, batch_size=32, show_progress_bar=False)
    return np.asarray(v, dtype=np.float32)


def embed_queries(texts: list[str]) -> np.ndarray:
    return _encode(texts, "query: ")


def embed_passages(texts: list[str]) -> np.ndarray:
    return _encode(texts, "passage: ")


def model_name() -> str:
    return get_settings().embedding_model
