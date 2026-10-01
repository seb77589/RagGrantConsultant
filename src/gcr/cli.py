"""Command line entry points."""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Annotated

import typer

from . import config
from .sources import cordis

app = typer.Typer(add_completion=False, help="Grant consultant ingestion pipeline.")


@app.callback()
def _main() -> None:
    """Ensure the data directories exist before any command runs."""
    config.ensure_dirs()


@app.command()
def fetch(
    dataset: Annotated[str, typer.Argument(help="cordis dataset: horizon or h2020")] = "horizon",
    force: Annotated[
        bool, typer.Option(help="re-download even if unchanged upstream")
    ] = False,
) -> None:
    """Download a CORDIS bulk dataset and record it in the source manifest."""
    from .fetch import download

    if dataset not in cordis.DATASETS:
        raise typer.BadParameter(
            f"unknown dataset {dataset!r}; choose from {list(cordis.DATASETS)}"
        )
    spec = cordis.DATASETS[dataset]
    url = str(spec["url"])
    dest = config.DATA_RAW / "cordis" / url.rsplit("/", 1)[-1]

    record = download(
        url,
        dest,
        source_system=cordis.SOURCE_SYSTEM,
        licence=cordis.LICENCE,
        attribution=cordis.ATTRIBUTION,
        force=force,
        note=f"dataset={dataset} programme={spec['programme']}",
    )
    typer.echo(f"{record.path}  {record.bytes:,} bytes  sha256={record.sha256[:16]}...")
    typer.echo(f"upstream last-modified: {record.upstream_last_modified}")


def _source_fetch_date(url: str):
    """When the payload behind `url` was actually downloaded, per the manifest.

    Returns None when the manifest has no record, which leaves the adapter's
    own `datetime.now(UTC)` default in place -- the only honest answer when we
    have no evidence of an earlier fetch.
    """
    from .manifest import latest_for
    from .sources.cordis import SOURCE_SYSTEM

    record = latest_for(SOURCE_SYSTEM, url)
    return record.fetch_date if record else None


@app.command()
def sections(
    dataset: Annotated[str, typer.Argument()] = "horizon",
    limit: Annotated[int, typer.Option(help="stop after N projects (0 = all)")] = 0,
    out: Annotated[Path | None, typer.Option(help="write sections as JSONL")] = None,
    allow_token_heuristic: Annotated[
        bool,
        typer.Option(
            "--allow-token-heuristic",
            help="count tokens by character estimate when the bge-m3 tokenizer is absent; "
            "produces a different corpus, so never use it for output that will be embedded",
        ),
    ] = False,
) -> None:
    """Build sections and report the corpus profile."""
    from .chunking import require_real_tokenizer, tokenizer_name

    # Before any work: the tokenizer decides chunk boundaries, so getting this
    # wrong changes the corpus rather than merely the reported counts.
    if not allow_token_heuristic:
        require_real_tokenizer()

    spec = cordis.DATASETS[dataset]
    zip_path = config.DATA_RAW / "cordis" / str(spec["url"]).rsplit("/", 1)[-1]
    if not zip_path.exists():
        raise typer.BadParameter(f"{zip_path} not found; run: gcr fetch {dataset}")

    # fetch_date means "when we retrieved the source", which drives "as of"
    # dates and staleness warnings. It is NOT when sections were built: a
    # corpus rebuilt today from a two-year-old download is two years stale, and
    # defaulting to now() would report it as fresh. The manifest holds the real
    # date, so take it from there and fall back only when there is no record.
    fetched = _source_fetch_date(str(spec["url"]))

    n = 0
    tokens = 0
    by_origin: dict[str, int] = {}
    countries: set[str] = set()
    missing_country = 0
    missing_source_date = 0
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
    handle = out.open("w", encoding="utf-8") if out else None

    try:
        for s in cordis.iter_sections(
            zip_path, dataset=dataset, limit=limit or None, fetch_date=fetched
        ):
            n += 1
            tokens += s.token_count
            by_origin[s.origin.value] = by_origin.get(s.origin.value, 0) + 1
            if s.country:
                countries.add(s.country)
            else:
                missing_country += 1
            if s.source.source_date is None:
                missing_source_date += 1
            if handle:
                handle.write(s.model_dump_json() + "\n")
    finally:
        if handle:
            handle.close()

    # Recorded in the profile so a pasted run is self-describing: two runs that
    # disagree on section count are explained by this line before anything else.
    typer.echo(f"token counter       : {tokenizer_name()}")
    typer.echo(f"chunking version    : {config.CHUNKING_VERSION}")
    typer.echo(f"sections            : {n:,}")
    typer.echo(f"tokens              : {tokens:,}")
    typer.echo(f"mean tokens/section : {tokens / n:.0f}" if n else "mean tokens/section : n/a")
    typer.echo(f"by origin           : {by_origin}")
    typer.echo(f"distinct countries  : {len(countries)}")
    typer.echo(f"sections w/o country: {missing_country:,}")
    typer.echo(f"sections w/o date   : {missing_source_date:,}")
    if n > config.CORE_SECTION_CAP:
        typer.secho(
            f"warning: {n:,} exceeds the core cap of {config.CORE_SECTION_CAP:,}",
            fg=typer.colors.YELLOW,
        )
    if out:
        typer.echo(f"written             : {out}")


@app.command("benchmark-embed")
def benchmark_embed(
    dataset: Annotated[str, typer.Argument()] = "horizon",
    n: Annotated[int, typer.Option(help="sections to embed")] = 10_000,
    batch_size: Annotated[int, typer.Option()] = config.EMBED_BATCH_SIZE,
    fp16: Annotated[bool, typer.Option()] = True,
    seed: Annotated[int, typer.Option()] = 0,
    out: Annotated[Path | None, typer.Option(help="write the result as JSON")] = None,
) -> None:
    """Measure bge-m3 throughput on a real sample, per the report's caveat."""
    from .embed import benchmark

    spec = cordis.DATASETS[dataset]
    zip_path = config.DATA_RAW / "cordis" / str(spec["url"]).rsplit("/", 1)[-1]
    if not zip_path.exists():
        raise typer.BadParameter(f"{zip_path} not found; run: gcr fetch {dataset}")

    # Reservoir sample so the measurement is not biased to the first projects.
    rng = random.Random(seed)
    sample: list[str] = []
    for i, s in enumerate(cordis.iter_sections(zip_path, dataset=dataset)):
        if len(sample) < n:
            sample.append(s.text)
        else:
            j = rng.randrange(i + 1)
            if j < n:
                sample[j] = s.text

    typer.echo(f"sampled {len(sample):,} sections; embedding...")
    result = benchmark(sample, batch_size=batch_size, fp16=fp16)
    typer.echo(result.render())
    if out:
        out.write_text(json.dumps(result.__dict__, indent=2, default=str), encoding="utf-8")
        typer.echo(f"written: {out}")


@app.command()
def manifest() -> None:
    """Show the recorded source manifest."""
    from .manifest import read_all

    records = read_all()
    if not records:
        typer.echo("manifest is empty")
        return
    for r in records:
        typer.echo(
            f"{r.fetch_date:%Y-%m-%d %H:%M}  {r.source_system:>8}  "
            f"{r.bytes:>12,}  {r.sha256[:12]}  {r.url}"
        )


if __name__ == "__main__":
    app()


@app.command()
def load(
    dataset: Annotated[str, typer.Argument()] = "horizon",
    limit: Annotated[int, typer.Option(help="stop after N projects (0 = all)")] = 0,
    batch_size: Annotated[int, typer.Option()] = config.EMBED_BATCH_SIZE,
    embed: Annotated[bool, typer.Option(help="compute embeddings while loading")] = True,
    truncate: Annotated[bool, typer.Option(help="empty the table first")] = False,
) -> None:
    """Load sections into PostgreSQL, embedding them on the way in."""
    from .chunking import require_real_tokenizer
    from .db import connect, insert_sections, record_run, table_stats
    from .manifest import latest_for

    require_real_tokenizer()

    spec = cordis.DATASETS[dataset]
    url = str(spec["url"])
    zip_path = config.DATA_RAW / "cordis" / url.rsplit("/", 1)[-1]
    if not zip_path.exists():
        raise typer.BadParameter(f"{zip_path} not found; run: gcr fetch {dataset}")

    record = latest_for(cordis.SOURCE_SYSTEM, url)
    fetched = record.fetch_date if record else None

    sections = list(
        cordis.iter_sections(zip_path, dataset=dataset, limit=limit or None, fetch_date=fetched)
    )
    typer.echo(f"sections to load    : {len(sections):,}")

    vectors = None
    if embed:
        from .embed import embed_texts, load_model

        typer.echo(f"embedding with      : {config.EMBED_MODEL} (batch {batch_size})")
        model = load_model(fp16=True)
        vectors = embed_texts(model, [s.text for s in sections], batch_size=batch_size)

    with connect() as conn:
        if truncate:
            with conn.cursor() as cur:
                cur.execute(f"TRUNCATE {config.SECTIONS_TABLE}")
        written = insert_sections(
            conn, sections, vectors, chunking_version=config.CHUNKING_VERSION
        )
        run_id = record_run(
            conn,
            source_system=cordis.SOURCE_SYSTEM,
            dataset=dataset,
            source_sha256=record.sha256 if record else None,
            chunking_version=config.CHUNKING_VERSION,
            embed_model=config.EMBED_MODEL if embed else "none",
            sections_written=written,
            note=f"limit={limit or 'all'}",
        )
        conn.commit()
        stats = table_stats(conn)

    typer.echo(f"rows written        : {written:,}  (run {run_id})")
    typer.echo(f"rows in table       : {stats['rows']:,}  embedded: {stats['embedded']:,}")
    typer.echo(f"table size          : {stats['size']}")


@app.command("build-index")
def build_index(
    m: Annotated[int, typer.Option(help="HNSW graph degree")] = 16,
    ef_construction: Annotated[int, typer.Option()] = 64,
) -> None:
    """Build the HNSW index and report how long it took."""
    from .db import build_hnsw, connect, table_stats

    with connect() as conn:
        before = table_stats(conn)
        typer.echo(f"rows                : {before['rows']:,} ({before['embedded']:,} embedded)")
        typer.echo(f"building HNSW       : m={m} ef_construction={ef_construction}")
        seconds = build_hnsw(conn, m=m, ef_construction=ef_construction)
        after = table_stats(conn)

    typer.echo(f"build time          : {seconds:.1f} s")
    typer.echo(f"table + indexes     : {after['size']}")
    for name, size in after["indexes"].items():
        typer.echo(f"  {name:38s} {size}")


@app.command()
def search(
    query: Annotated[str, typer.Argument(help="the question")],
    mode: Annotated[str, typer.Option(help="hybrid | vector | fulltext")] = "hybrid",
    country: Annotated[str | None, typer.Option(help="ISO-2 eligibility filter")] = None,
    groups: Annotated[str, typer.Option(help="comma-separated access groups")] = "public",
    limit: Annotated[int, typer.Option()] = 10,
    as_json_out: Annotated[bool, typer.Option("--json", help="machine-readable")] = False,
) -> None:
    """Retrieve sections. Access filtering happens in SQL, never in a prompt."""
    from .db import as_json, connect, search_fulltext, search_hybrid, search_vector

    group_list = [g.strip() for g in groups.split(",") if g.strip()]

    vector = None
    if mode in ("hybrid", "vector"):
        from .embed import embed_texts, load_model

        vector = embed_texts(load_model(fp16=True), [query])[0]

    with connect() as conn:
        if mode == "fulltext":
            hits = search_fulltext(conn, query, group_list, country, limit=limit)
        elif mode == "vector":
            hits = search_vector(conn, vector, group_list, country, limit=limit)
        elif mode == "hybrid":
            hits = search_hybrid(conn, query, vector, group_list, country, limit=limit)
        else:
            raise typer.BadParameter(f"unknown mode {mode!r}")

    if as_json_out:
        typer.echo(as_json(hits))
        return
    typer.echo(f"mode={mode} groups={group_list} country={country or 'any'} hits={len(hits)}")
    for i, h in enumerate(hits, 1):
        typer.echo(f"\n{i}. [{h.score:.4f}] {h.citation()}")
        typer.echo(f"   {h.text[:200].replace(chr(10), ' ')}")
