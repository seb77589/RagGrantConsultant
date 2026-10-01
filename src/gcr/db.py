"""PostgreSQL + pgvector access.

Keeps three things honest:

* **Access filtering is SQL, not prompting.** Every retrieval function takes the
  caller's groups and filters on `access_group` in the query. A model
  instruction is not an access control.
* **The two tiers stay apart.** Core and translated are separate tables with
  separate indexes, per the Kohesio rule, and nothing here joins them.
* **Identity travels with the text.** Retrieval returns the source identifier,
  source date and fetch date alongside each section, because an answer without
  them cannot be cited or dated.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from typing import Any

from .config import DATABASE_URL, EMBED_DIM, SECTIONS_TABLE
from .models import Section

# The group every row carries unless something narrower is set. Rows readable
# by anyone who can log in at all.
PUBLIC_GROUP = "public"


@contextmanager
def connect(dsn: str | None = None) -> Iterator[Any]:
    """A connection with pgvector's types registered.

    Imported lazily so that `gcr --help`, the chunking tests and the lint path
    do not require a database driver to be importable.
    """
    import psycopg

    conn = psycopg.connect(dsn or DATABASE_URL)
    try:
        yield conn
    finally:
        conn.close()


def _vector_literal(vec: Sequence[float]) -> str:
    """pgvector's text input format. Cheaper than a round trip through a
    registered type for bulk COPY, and it keeps psycopg's adapter optional."""
    return "[" + ",".join(f"{v:.7g}" for v in vec) + "]"


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def insert_sections(
    conn: Any,
    sections: Iterable[Section],
    embeddings: Iterable[Sequence[float]] | None,
    chunking_version: str,
    access_group: str = PUBLIC_GROUP,
    table: str = SECTIONS_TABLE,
) -> int:
    """Bulk-insert via COPY, which is an order of magnitude faster than execute
    per row at this corpus size.

    `embeddings` may be None, in which case rows land with a NULL embedding and
    the partial index `sections_embedding_missing` makes them cheap to find.
    """
    columns = (
        "section_id", "source_system", "source_id", "source_url", "source_date",
        "fetch_date", "licence", "attribution", "text", "origin", "country",
        "nuts_code", "programme", "programme_period", "part", "ordinal",
        "token_count", "access_group", "chunking_version", "embedding",
    )
    vectors = iter(embeddings) if embeddings is not None else None
    written = 0

    with conn.cursor() as cur, cur.copy(
        f"COPY {table} ({', '.join(columns)}) FROM STDIN"
    ) as copy:
        for s in sections:
            vec = next(vectors) if vectors is not None else None
            if vec is not None and len(vec) != EMBED_DIM:
                raise ValueError(
                    f"embedding for {s.section_id} has {len(vec)} dimensions, "
                    f"expected {EMBED_DIM}"
                )
            copy.write_row(
                (
                    s.section_id,
                    s.source.source_system,
                    s.source.source_id,
                    s.source.source_url,
                    s.source.source_date,
                    s.source.fetch_date,
                    s.source.licence,
                    s.source.attribution,
                    s.text,
                    s.origin.value,
                    s.country,
                    s.nuts_code,
                    s.programme,
                    s.programme_period.value,
                    s.part,
                    s.ordinal,
                    s.token_count,
                    access_group,
                    chunking_version,
                    _vector_literal(vec) if vec is not None else None,
                )
            )
            written += 1
    return written


def record_run(
    conn: Any,
    source_system: str,
    dataset: str,
    source_sha256: str | None,
    chunking_version: str,
    embed_model: str,
    sections_written: int,
    note: str | None = None,
) -> int:
    """Tie the rows just written to the payload and versions that produced them,
    which is what makes the migration comparison auditable."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO ingestion_runs
                (finished_at, source_system, dataset, source_sha256,
                 chunking_version, embed_model, sections_written, note)
            VALUES (now(), %s, %s, %s, %s, %s, %s, %s)
            RETURNING run_id
            """,
            (source_system, dataset, source_sha256, chunking_version,
             embed_model, sections_written, note),
        )
        return cur.fetchone()[0]


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Hit:
    """One retrieved section, carrying everything a citation needs.

    `licence`, `attribution`, `origin` and `programme_period` are here because
    an answer cannot be made compliant without them, and they were previously
    written at ingestion but never read back:

    * CLAUDE.md requires "© European Union" with the source link on *every cited
      source*, which means `attribution` and `licence` must travel with the text
      rather than be looked up again.
    * The Kohesio rule requires the translated tier to be *labelled in answers*,
      which needs `origin`.

    Field order is load-bearing: all three search functions build hits as
    `Hit(*row)` from `_SELECT` plus a trailing score, so this list and `_SELECT`
    must stay in the same order.
    """

    section_id: str
    source_system: str
    source_id: str
    source_url: str
    source_date: Any
    fetch_date: Any
    country: str | None
    programme: str | None
    programme_period: str | None
    origin: str
    licence: str
    attribution: str
    text: str
    score: float

    def citation(self) -> str:
        """Short form, for terminal output and logs."""
        return f"{self.source_system}:{self.source_id} ({self.as_of()}) {self.source_url}"

    def as_of(self) -> str:
        """The date a reader should judge this text by.

        Never silently substitutes the fetch date: a document with no upstream
        date says so, because claiming an "as of" we do not have is the same
        class of error as inventing a figure.
        """
        return self.source_date.isoformat() if self.source_date else "no upstream date"

    def attributed_citation(self) -> str:
        """Full form, as it must appear beside a quote in an answer."""
        return f"{self.citation()} — {self.attribution} ({self.licence})"

    def is_translated(self) -> bool:
        return self.origin == "machine_translated"


# Order must match the Hit field order above, up to but excluding `score`.
_SELECT = """
    section_id, source_system, source_id, source_url, source_date,
    fetch_date, country, programme, programme_period, origin,
    licence, attribution, text
"""


def _filters(
    groups: Sequence[str], country: str | None, programme_period: str | None
) -> tuple[str, list[Any]]:
    """Structured eligibility filter, applied before ranking.

    `groups` is never optional: a caller that does not say who it is gets the
    public tier only, rather than everything.
    """
    clauses = ["access_group = ANY(%s)"]
    params: list[Any] = [list(groups) if groups else [PUBLIC_GROUP]]
    if country:
        clauses.append("(country = %s OR country IS NULL)")
        params.append(country.upper())
    if programme_period:
        clauses.append("programme_period = %s")
        params.append(programme_period)
    return " AND ".join(clauses), params


def search_fulltext(
    conn: Any,
    query: str,
    groups: Sequence[str] = (PUBLIC_GROUP,),
    country: str | None = None,
    programme_period: str | None = None,
    limit: int = 20,
    table: str = SECTIONS_TABLE,
) -> list[Hit]:
    where, params = _filters(groups, country, programme_period)
    sql = f"""
        SELECT {_SELECT}, ts_rank_cd(tsv, websearch_to_tsquery('english', %s)) AS score
        FROM {table}
        WHERE {where} AND tsv @@ websearch_to_tsquery('english', %s)
        ORDER BY score DESC
        LIMIT %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, [query, *params, query, limit])
        return [Hit(*row) for row in cur.fetchall()]


def _tune_hnsw_for_filtering(cur: Any, limit: int) -> None:
    """Make filtered vector search actually return rows.

    HNSW is an approximate index: it walks the graph, returns `ef_search`
    candidates, and only then does PostgreSQL apply the WHERE clause. With a
    selective structured filter that post-filtering empties the result. Measured
    on this corpus, where Ireland is 1,260 of 50,940 sections (2.5%):

        Index Scan using sections_embedding_hnsw
          Filter: country = 'IE' OR country IS NULL
          Rows Removed by Filter: 40
          rows=0

    Forty candidates in, forty discarded, nothing out -- for a query with 1,260
    perfectly good matches. Not a slow query: a silently empty one, and the
    eligibility filter (country, NUTS, programme) is applied to *every* real
    retrieval, so this would have affected nearly all of them.

    `hnsw.iterative_scan` (pgvector 0.8.0+, and the image carries 0.8.6) makes
    the scan resume and fetch more candidates until the limit is satisfied.
    `relaxed_order` rather than `strict_order` because results are reranked
    downstream anyway, and relaxed is markedly faster.
    """
    # set_config(..., is_local => true) rather than SET LOCAL, because SET does
    # not accept bind parameters and these values depend on `limit`.
    cur.execute("SELECT set_config('hnsw.iterative_scan', 'relaxed_order', true)")
    # The ceiling on how far a resumed scan will go. Generous relative to the
    # limit, bounded so a filter that matches nothing cannot walk the whole
    # graph.
    cur.execute(
        "SELECT set_config('hnsw.max_scan_tuples', %s, true)",
        (str(max(20_000, limit * 200)),),
    )
    cur.execute("SELECT set_config('hnsw.ef_search', %s, true)", (str(max(40, limit * 4)),))


def search_vector(
    conn: Any,
    embedding: Sequence[float],
    groups: Sequence[str] = (PUBLIC_GROUP,),
    country: str | None = None,
    programme_period: str | None = None,
    limit: int = 20,
    table: str = SECTIONS_TABLE,
) -> list[Hit]:
    where, params = _filters(groups, country, programme_period)
    # 1 - cosine distance, so bigger is better and the two halves of the hybrid
    # score point the same way.
    sql = f"""
        SELECT {_SELECT}, 1 - (embedding <=> %s::vector) AS score
        FROM {table}
        WHERE {where} AND embedding IS NOT NULL
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """
    vec = _vector_literal(embedding)
    with conn.cursor() as cur:
        _tune_hnsw_for_filtering(cur, limit)
        cur.execute(sql, [vec, *params, vec, limit])
        return [Hit(*row) for row in cur.fetchall()]


def search_hybrid(
    conn: Any,
    query: str,
    embedding: Sequence[float],
    groups: Sequence[str] = (PUBLIC_GROUP,),
    country: str | None = None,
    programme_period: str | None = None,
    limit: int = 10,
    candidates: int = 50,
    k: int = 60,
    table: str = SECTIONS_TABLE,
) -> list[Hit]:
    """Keyword and vector results merged by reciprocal rank fusion.

    RRF rather than a weighted sum of scores: ts_rank_cd and cosine similarity
    are not on comparable scales, and any fixed weighting between them would be
    a guess that quietly favours one half. RRF needs only the orderings.
    """
    lexical = search_fulltext(conn, query, groups, country, programme_period, candidates, table)
    dense = search_vector(conn, embedding, groups, country, programme_period, candidates, table)

    ranked: dict[str, float] = {}
    hits: dict[str, Hit] = {}
    for results in (lexical, dense):
        for rank, hit in enumerate(results, start=1):
            ranked[hit.section_id] = ranked.get(hit.section_id, 0.0) + 1.0 / (k + rank)
            hits[hit.section_id] = hit

    top = sorted(ranked.items(), key=lambda kv: kv[1], reverse=True)[:limit]
    # `replace` rather than re-listing every field positionally: Hit has grown
    # once already, and a positional rebuild silently mis-assigns fields the
    # next time it grows.
    #
    # Note what the returned score now means. It is a fusion artefact -- a sum
    # of reciprocal ranks -- not a relevance score, so it is comparable only
    # within one query's results. Downstream reranking replaces it.
    return [replace(hits[section_id], score=score) for section_id, score in top]


# ---------------------------------------------------------------------------
# Index management
# ---------------------------------------------------------------------------


def build_hnsw(conn: Any, table: str = SECTIONS_TABLE, m: int = 16, ef_construction: int = 64):
    """Build the HNSW index, after the bulk load rather than before.

    Building first and then inserting is far slower, and pgvector 0.6.0+ builds
    in parallel, so this wants the rows already present. Returns seconds taken,
    because how long it takes is itself one of the open questions.
    """
    import time

    with conn.cursor() as cur:
        # maintenance_work_mem governs whether the build fits in memory; the
        # published rule of thumb is vectors x dims x 4 bytes x 2.
        cur.execute("SET maintenance_work_mem = '2GB'")
        cur.execute("SET max_parallel_maintenance_workers = 4")
        start = time.perf_counter()
        cur.execute(
            f"CREATE INDEX IF NOT EXISTS {table}_embedding_hnsw "
            f"ON {table} USING hnsw (embedding vector_cosine_ops) "
            f"WITH (m = {m}, ef_construction = {ef_construction})"
        )
        conn.commit()
        return time.perf_counter() - start


def table_stats(conn: Any, table: str = SECTIONS_TABLE) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT count(*), count(embedding), pg_size_pretty(pg_total_relation_size('{table}'))"
            f" FROM {table}"
        )
        rows, embedded, size = cur.fetchone()
        cur.execute(
            "SELECT indexname, pg_size_pretty(pg_relation_size(indexname::regclass)) "
            "FROM pg_indexes WHERE tablename = %s ORDER BY indexname",
            (table,),
        )
        indexes = dict(cur.fetchall())
    return {"rows": rows, "embedded": embedded, "size": size, "indexes": indexes}


def as_json(hits: Sequence[Hit]) -> str:
    """Machine-readable hits, carrying everything a citation needs.

    Attribution and licence are included rather than dropped: anything that
    consumes this is a step away from showing the text to someone, and the
    attribution rule applies to every cited source.
    """
    return json.dumps(
        [
            {
                "section_id": h.section_id,
                "citation": h.citation(),
                "source_url": h.source_url,
                "as_of": h.as_of(),
                "attribution": h.attribution,
                "licence": h.licence,
                "country": h.country,
                "programme": h.programme,
                "programme_period": h.programme_period,
                "origin": h.origin,
                "translated": h.is_translated(),
                "score": round(h.score, 6),
                "text": h.text[:300],
            }
            for h in hits
        ],
        indent=2,
        ensure_ascii=False,
    )
