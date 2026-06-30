"""BM25 lexical scoring over a job-description corpus (rank_bm25)."""

import re
from typing import List

from rank_bm25 import BM25Okapi

_TOKEN = re.compile(r"[a-z0-9+#.]+")


def tokenize(text: str) -> List[str]:
    return _TOKEN.findall((text or "").lower())


class BM25Index:
    """A BM25 index over a fixed list of documents, scored against a query."""

    def __init__(self, documents: List[str]):
        self.tokenized = [tokenize(d) for d in documents]
        # BM25Okapi requires a non-empty corpus with at least one non-empty doc.
        self._bm25 = BM25Okapi(self.tokenized) if any(self.tokenized) else None

    def scores(self, query: str) -> List[float]:
        """Raw BM25 scores aligned to the documents (all zeros if corpus/query empty)."""
        if self._bm25 is None:
            return [0.0] * len(self.tokenized)
        q = tokenize(query)
        if not q:
            return [0.0] * len(self.tokenized)
        return [float(s) for s in self._bm25.get_scores(q)]

    def normalized_scores(self, query: str) -> List[float]:
        """BM25 scores scaled to 0..1 by the batch maximum (0 if all zero)."""
        raw = self.scores(query)
        top = max(raw) if raw else 0.0
        if top <= 0:
            return [0.0] * len(raw)
        return [s / top for s in raw]
