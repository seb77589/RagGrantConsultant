"""Clients for the three model services.

One function per call, no classes and no shared session: these are called a
handful of times per question, so connection reuse buys nothing worth the state.

**No fallbacks.** If a service is unreachable this raises. The temptation is to
fall back to an in-process model when the embedding service is down, and that
would be the same defect that cost us the corpus once already: the character
tokenizer fallback in `chunking` silently produced a *different* corpus and
reported success. A silent switch between encoders would equally silently
degrade retrieval, because the index was built with one and the query would be
encoded by the other. Better to fail with the URL in the message.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from .config import (
    EMBED_MODEL,
    LLM_MAX_TOKENS,
    LLM_TEMPERATURE,
    LLM_URL,
    TEI_EMBED_URL,
    TEI_RERANK_URL,
)

# Embedding and reranking are fast (single-digit milliseconds measured) and a
# hang should surface quickly. Generation is not: several hundred tokens at a
# few dozen tokens per second on a laptop GPU.
FAST_TIMEOUT = 30.0
GENERATION_TIMEOUT = 300.0

# Must not exceed tei-rerank's --max-client-batch-size, which it enforces with
# HTTP 422. Kept below the configured 64 so the two can drift apart a little
# without breaking.
RERANK_BATCH_SIZE = 32


class ServiceUnavailable(RuntimeError):
    """A model service could not be reached, or answered unusably.

    Carries the service name and URL because the first question on seeing this
    is always "which one, and at what address" -- the answer differs between a
    host-side run and one inside the compose network.
    """

    def __init__(self, service: str, url: str, detail: str) -> None:
        super().__init__(
            f"{service} at {url} is unavailable: {detail}\n"
            f"  check: docker compose --profile models ps"
        )
        self.service = service
        self.url = url


def _post(service: str, url: str, payload: dict[str, Any], timeout: float) -> Any:
    import httpx

    try:
        response = httpx.post(url, json=payload, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        raise ServiceUnavailable(
            service, url, f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"
        ) from exc
    except httpx.HTTPError as exc:
        raise ServiceUnavailable(service, url, str(exc)) from exc


def embed_query(text: str) -> list[float]:
    """Embed one query through TEI, using the same weights as the index.

    TEI listens on port 80 inside its container, not 8080 -- a detail that costs
    an afternoon if assumed.
    """
    url = f"{TEI_EMBED_URL}/v1/embeddings"
    data = _post(
        "tei-embed", url, {"input": [text], "model": EMBED_MODEL}, FAST_TIMEOUT
    )
    try:
        return data["data"][0]["embedding"]
    except (KeyError, IndexError) as exc:
        raise ServiceUnavailable("tei-embed", url, f"unexpected response shape: {exc}") from exc


def rerank(query: str, texts: Sequence[str]) -> list[tuple[int, float]]:
    """Score each text against the query. Returns `(index into texts, score)`.

    TEI's own route; there is no OpenAI-compatible rerank endpoint, so this
    cannot be swapped for a generic client.

    Requests are split into batches because TEI enforces a server-side
    `--max-client-batch-size` and rejects anything larger with HTTP 422. Sending
    50 candidates to a service configured for 32 failed outright, and tying the
    breadth of retrieval to a serving flag is a coupling worth removing: the
    scores are per (query, text) pair, so batching changes nothing about the
    result. Indices are offset back to the caller's list.
    """
    if not texts:
        return []
    url = f"{TEI_RERANK_URL}/rerank"
    out: list[tuple[int, float]] = []
    for start in range(0, len(texts), RERANK_BATCH_SIZE):
        batch = list(texts[start : start + RERANK_BATCH_SIZE])
        data = _post(
            "tei-rerank",
            url,
            {"query": query, "texts": batch, "raw_scores": False},
            FAST_TIMEOUT,
        )
        try:
            out.extend((start + int(item["index"]), float(item["score"])) for item in data)
        except (KeyError, TypeError, ValueError) as exc:
            raise ServiceUnavailable(
                "tei-rerank", url, f"unexpected response shape: {exc}"
            ) from exc
    return out


def chat(
    messages: Sequence[dict[str, str]],
    max_tokens: int = LLM_MAX_TOKENS,
    temperature: float = LLM_TEMPERATURE,
) -> str:
    """One generation turn against the OpenAI-compatible endpoint."""
    url = f"{LLM_URL}/v1/chat/completions"
    data = _post(
        "llm",
        url,
        {
            "messages": list(messages),
            "max_tokens": max_tokens,
            "temperature": temperature,
            # The server is configured with --reasoning off, but a client that
            # does not depend on server flags is one less coupling.
            "stream": False,
        },
        GENERATION_TIMEOUT,
    )
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise ServiceUnavailable("llm", url, f"unexpected response shape: {exc}") from exc
