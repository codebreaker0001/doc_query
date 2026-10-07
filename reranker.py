from sentence_transformers import CrossEncoder

_reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")


def rerank(query: str, chunks: list[str], top_k: int = 3) -> list[str]:
    if not chunks:
        return []

    pairs = [[query, chunk] for chunk in chunks]
    scores = _reranker.predict(pairs)

    ranked = sorted(zip(chunks, scores), key=lambda pair: pair[1], reverse=True)
    return [chunk for chunk, _ in ranked[:top_k]]
