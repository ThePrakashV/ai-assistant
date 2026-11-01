import os

# Windows la torch + faiss rendum OpenMP library load pannum bodhu
# "libiomp5md.dll already initialized" error varum. Idhu andha error ah thadukkum.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

from functools import lru_cache

import numpy as np
from sentence_transformers import SentenceTransformer

from app.core.config import settings


@lru_cache(maxsize=1)
def get_embedder() -> SentenceTransformer:
    """Model ah oru dhadavai mattum load pannum (apparam same object reuse)."""
    print(f"Loading embedding model '{settings.embed_model}' ...")
    return SentenceTransformer(settings.embed_model, device="cpu")


def embed(texts: list[str]) -> np.ndarray:
    """Texts -> normalized float32 vectors. (dot product = cosine similarity)"""
    vectors = get_embedder().encode(
        texts, normalize_embeddings=True, convert_to_numpy=True
    )
    return np.ascontiguousarray(vectors, dtype="float32")


def embed_dim() -> int:
    return int(get_embedder().get_sentence_embedding_dimension())