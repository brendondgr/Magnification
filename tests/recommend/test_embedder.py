"""
Real-model embedder test. Skips when the bge model can't be loaded (offline / not cached)
so the suite stays green without network. When it runs, it verifies dims + similarity.
"""

import os

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


# ---- model-load hardening (offline; no real model constructed) ----

def test_resolve_cache_dir_defaults_persistent(monkeypatch, tmp_path):
    """Default cache is ~/.cache/fastembed (persistent), never $TMPDIR/fastembed_cache."""
    monkeypatch.delenv("FASTEMBED_CACHE_PATH", raising=False)
    monkeypatch.setattr(embedder.Path, "home", staticmethod(lambda: tmp_path))
    assert embedder._resolve_cache_dir() == str(tmp_path / ".cache" / "fastembed")


def test_resolve_cache_dir_honors_env(monkeypatch):
    monkeypatch.setenv("FASTEMBED_CACHE_PATH", "/custom/fe/cache")
    assert embedder._resolve_cache_dir() == "/custom/fe/cache"


def test_get_model_forces_anonymous_and_persistent_cache(monkeypatch):
    """
    get_model disables the implicit HF token (so a stale ~/.cache/huggingface/token can't 401
    the public download) and passes the persistent cache_dir — without constructing the real
    model or touching the network.
    """
    monkeypatch.delenv("HF_HUB_DISABLE_IMPLICIT_TOKEN", raising=False)
    monkeypatch.setattr(embedder, "_model", None)
    monkeypatch.setattr(embedder, "_resolve_cache_dir", lambda: "/persistent/cache")

    captured = {}

    class FakeTextEmbedding:
        def __init__(self, model_name, cache_dir=None, **kwargs):
            captured["model_name"] = model_name
            captured["cache_dir"] = cache_dir

    import fastembed
    monkeypatch.setattr(fastembed, "TextEmbedding", FakeTextEmbedding)

    embedder.get_model()
    try:
        assert captured["model_name"] == embedder.MODEL_NAME
        assert captured["cache_dir"] == "/persistent/cache"
        assert os.environ.get("HF_HUB_DISABLE_IMPLICIT_TOKEN") == "1"
    finally:
        embedder._model = None
