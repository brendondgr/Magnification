"""
CPU embeddings via fastembed (BAAI/bge-small-en-v1.5).

The model is a lazily-loaded process-wide singleton (it downloads ~130 MB from HuggingFace
on first use and caches under ~/.cache). Embeddings are batched and can be computed in
parallel across CPU cores. Vectors are stored in the DB as packed float32 bytes.
"""

import struct
import threading
from typing import List, Optional, Sequence

MODEL_NAME = "BAAI/bge-small-en-v1.5"
EMBED_DIM = 384

_model = None
_lock = threading.Lock()


def get_model():
    """Return the shared TextEmbedding model, loading it on first call."""
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                from fastembed import TextEmbedding
                _model = TextEmbedding(model_name=MODEL_NAME)
    return _model


def embed_texts(texts: Sequence[str], batch_size: int = 32,
                parallel: Optional[int] = None) -> List[list]:
    """
    Embed a sequence of texts. Returns a list of float lists (length EMBED_DIM each).

    parallel: fastembed data-parallelism — >1 uses that many workers, 0 uses all cores,
    None disables. Empty/blank texts are embedded as-is (the model handles them).
    """
    if not texts:
        return []
    model = get_model()
    # fastembed yields numpy arrays; normalize the kwarg (parallel must be a positive int,
    # 0 for all cores, or None).
    par = parallel if (parallel is None or parallel >= 0) else None
    vectors = model.embed(list(texts), batch_size=batch_size, parallel=par)
    return [list(map(float, v)) for v in vectors]


def embed_text(text: str) -> list:
    """Embed a single text, returning a float list."""
    out = embed_texts([text])
    return out[0] if out else []


# ---- serialization (DB stores packed float32 bytes) ----

def to_bytes(vector: Sequence[float]) -> bytes:
    """Pack a float vector to little-endian float32 bytes."""
    vec = list(vector)
    return struct.pack(f"<{len(vec)}f", *vec)


def from_bytes(blob: Optional[bytes]) -> Optional[list]:
    """Unpack float32 bytes back to a float list, or None."""
    if not blob:
        return None
    n = len(blob) // 4
    return list(struct.unpack(f"<{n}f", blob))


# ---- similarity ----

def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity of two vectors (0.0 if either is empty/zero)."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)
