"""BM25 ranking sanity checks."""

from utils.backend.recommend.bm25 import BM25Index, tokenize


def test_tokenize_keeps_tech_tokens():
    toks = tokenize("Python, C++ and Node.js!")
    assert "python" in toks
    assert "c++" in toks or "c" in toks  # punctuation-tolerant


def test_bm25_orders_by_relevance():
    docs = [
        "machine learning engineer working on healthcare models in python",
        "sales associate retail customer service",
        "python data engineer building pipelines",
    ]
    idx = BM25Index(docs)
    scores = idx.scores("python machine learning healthcare")
    assert scores[0] > scores[1]  # ML/healthcare doc beats sales doc
    assert scores[0] >= scores[2]


def test_bm25_normalized_range():
    # 3+ docs so the query terms have positive IDF (a term in exactly half the corpus
    # has IDF 0 in BM25Okapi, which would zero out every score).
    docs = ["python ml engineer", "java spring backend", "sales associate retail"]
    norm = BM25Index(docs).normalized_scores("python ml")
    assert max(norm) == 1.0
    assert all(0.0 <= s <= 1.0 for s in norm)


def test_bm25_empty_corpus_is_safe():
    idx = BM25Index(["", ""])
    assert idx.scores("anything") == [0.0, 0.0]
