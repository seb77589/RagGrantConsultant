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


@app.command()
def sections(
    dataset: Annotated[str, typer.Argument()] = "horizon",
    limit: Annotated[int, typer.Option(help="stop after N projects (0 = all)")] = 0,
    out: Annotated[Path | None, typer.Option(help="write sections as JSONL")] = None,
) -> None:
    """Build sections and report the corpus profile."""
    spec = cordis.DATASETS[dataset]
    zip_path = config.DATA_RAW / "cordis" / str(spec["url"]).rsplit("/", 1)[-1]
    if not zip_path.exists():
        raise typer.BadParameter(f"{zip_path} not found; run: gcr fetch {dataset}")

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
        for s in cordis.iter_sections(zip_path, dataset=dataset, limit=limit or None):
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
