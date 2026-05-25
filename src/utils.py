import hashlib
import math
import re

EMBEDDING_DIMENSIONS = 1536
TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+")


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 100) -> list[str]:
    """
    Slices raw note text into smaller overlapping chunks to preserve local context.
    """
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk)
        # Move the cursor forward by chunk size minus the overlap
        start += chunk_size - overlap

        # Break early if the next step is negligible or complete
        if start >= len(text) - overlap:
            break

    return chunks


async def get_mock_embedding(text: str) -> list[float]:
    """
    Generates a deterministic 1536-dimensional float vector
    using a hashed bag-of-words fallback when no AI embedding API is available.
    """
    tokens = TOKEN_RE.findall(text.lower())
    vector = [0.0] * EMBEDDING_DIMENSIONS

    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "big") % EMBEDDING_DIMENSIONS
        vector[idx] += 1.0

    magnitude = math.sqrt(sum(x * x for x in vector))
    if magnitude == 0:
        return vector

    return [x / magnitude for x in vector]
