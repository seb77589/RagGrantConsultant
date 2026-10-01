"""The retrieval path CLAUDE.md describes, end to end.

    structured eligibility filter -> hybrid keyword + vector -> merge -> rerank
    -> 6-10 sections into the generation context

The first three steps already exist in `db.search_hybrid`, which applies the
filter in SQL and merges the two halves by reciprocal rank fusion. This module
adds the fourth, and is the only place that knows both the database and the
model services.

Why rerank at all, when hybrid search already ranks: the RRF score
`db.search_hybrid` returns is a fusion artefact, a sum of reciprocal ranks. It
says "both halves liked this" and nothing about how well a passage answers the
question, and it is not comparable between queries. The cross-encoder reads the
query and the passage together and scores relevance directly. So the merge is
the cheap, rough step that casts a wide net, and reranking is the expensive,
accurate step that picks from it -- which is why `RETRIEVE_CANDIDATES` is
generous and `RERANK_TOP_K` is small.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import Any

from . import services
from .config import RERANK_TOP_K, RETRIEVE_CANDIDATES, SECTIONS_TABLE
from .db import PUBLIC_GROUP, Hit, search_hybrid


def rerank_hits(query: str, hits: Sequence[Hit], top_k: int = RERANK_TOP_K) -> list[Hit]:
    """Re-score `hits` against `query` with the cross-encoder, best first.

    Returns at most `top_k`, with `Hit.score` replaced by the rerank score. The
    replacement is deliberate: leaving an RRF score alongside a rerank score in
    the same field is how someone later compares two numbers that mean different
    things.
    """
    if not hits:
        return []
    scored = services.rerank(query, [h.text for h in hits])
    # TEI returns results already sorted by score, but sorting here means the
    # guarantee is ours rather than the service's.
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return [replace(hits[index], score=score) for index, score in scored[:top_k]]


def retrieve(
    conn: Any,
    query: str,
    groups: Sequence[str] = (PUBLIC_GROUP,),
    country: str | None = None,
    programme_period: str | None = None,
    top_k: int = RERANK_TOP_K,
    candidates: int = RETRIEVE_CANDIDATES,
    table: str = SECTIONS_TABLE,
) -> list[Hit]:
    """Filter, search, merge, rerank.

    `groups` carries the caller's access groups into the SQL filter. It is not
    optional and defaults to the public tier only: a caller that does not say
    who it is must not see everything.
    """
    embedding = services.embed_query(query)
    merged = search_hybrid(
        conn,
        query,
        embedding,
        groups,
        country,
        programme_period,
        limit=candidates,
        candidates=candidates,
        table=table,
    )
    return rerank_hits(query, merged, top_k=top_k)
