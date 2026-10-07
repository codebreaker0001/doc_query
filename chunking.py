import re

import tiktoken

_encoding = tiktoken.get_encoding("cl100k_base")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")


def split_into_sentences(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]


def split_into_chunks(pages: list[str], chunk_size: int = 500, sentence_overlap: int = 2) -> list[dict]:
    chunks = []
    for page_number, page_text in enumerate(pages, start=1):
        sentences = split_into_sentences(page_text)
        if not sentences:
            continue

        current_sentences: list[str] = []
        current_tokens = 0

        for sentence in sentences:
            sentence_tokens = len(_encoding.encode(sentence))

            if current_sentences and current_tokens + sentence_tokens > chunk_size:
                chunks.append({"text": " ".join(current_sentences), "page": page_number})
                # Carry the last couple of sentences into the next chunk so
                # a reader doesn't lose context right at the chunk boundary.
                current_sentences = current_sentences[-sentence_overlap:]
                current_tokens = sum(len(_encoding.encode(s)) for s in current_sentences)

            current_sentences.append(sentence)
            current_tokens += sentence_tokens

        if current_sentences:
            chunks.append({"text": " ".join(current_sentences), "page": page_number})

    return chunks
