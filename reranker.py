# Same reasoning as embed.py: the sentence_transformers import itself, not
# just the model constructor, is deferred into the function body so boot
# doesn't pay this cost before the app can even start.
_reranker = None


def _get_reranker():
    global _reranker
    if _reranker is None:
        from sentence_transformers import CrossEncoder

        _reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    return _reranker


def rerank(query: str, chunks: list[str], top_k: int = 3) -> list[str]:
    if not chunks:
        return []

    pairs = [[query, chunk] for chunk in chunks]
    scores = _get_reranker().predict(pairs)

    ranked = sorted(zip(chunks, scores), key=lambda pair: pair[1], reverse=True)
    return [chunk for chunk, _ in ranked[:top_k]]
