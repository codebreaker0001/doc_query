# The sentence_transformers import itself (not just constructing the model)
# pulls in torch/transformers and costs hundreds of MB resident -- deferred
# into the function body so that cost isn't paid until first actual use,
# not at process boot. Importing it at module level, even without
# constructing a model, was enough to tip the container over Render's
# 512MB free-tier limit before it could even bind a port.
_model = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer("BAAI/bge-small-en-v1.5")
    return _model


def embed_texts(texts: list[str]) -> list[list[float]]:
    embeddings = _get_model().encode(texts, normalize_embeddings=True)
    return embeddings.tolist()
