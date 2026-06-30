"""
Real-model embedder test. Skips when the bge model can't be loaded (offline / not cached)
so the suite stays green without network. When it runs, it verifies dims + similarity.
"""

import pytest

from utils.backend.recommend import embedder


@pytest.fixture(scope="module")
def model_vectors():
    try:
        vecs = embedder.embed_texts([
            "machine learning engineer for healthcare AI",
            "deep learning models in clinical medicine",
            "retail sales associate customer service",
        ])
    except Exception as e:  # model download/load failed (offline)
        pytest.skip(f"bge model unavailable: {e}")
    return vecs


def test_embedding_dimension(model_vectors):
    assert all(len(v) == embedder.EMBED_DIM for v in model_vectors)


def test_related_texts_are_more_similar(model_vectors):
    ml_health, dl_clinical, sales = model_vectors
    assert embedder.cosine(ml_health, dl_clinical) > embedder.cosine(ml_health, sales)


def test_byte_roundtrip():
    vec = [0.1, -0.2, 0.3, 0.4]
    assert embedder.from_bytes(embedder.to_bytes(vec)) == pytest.approx(vec)
    assert embedder.from_bytes(None) is None
