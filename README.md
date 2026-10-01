# RagGrantConsultant

A retrieval-augmented question-answering assistant for European public funding, built from
official, English-origin sources and answering only with citations, source dates and official
links.

Design rationale, corpus sizing, hardware limits and legal constraints live in
[`compass_artifact_wf-74a0c4d9-b271-53b8-93db-67162cf90f3f_text_markdown.md`](compass_artifact_wf-74a0c4d9-b271-53b8-93db-67162cf90f3f_text_markdown.md).
The rules that code must follow are summarised in [`CLAUDE.md`](CLAUDE.md).

**This assistant is an independent tool. It is not operated, endorsed or checked by the European
Commission, any European Union body or any national authority.** Source content © European Union
and other rightholders, reused under the terms indicated for each source.

## Status

Phase 1, early. The ingestion pipeline works end to end for CORDIS. The runtime stack
(PostgreSQL + pgvector, the login chain, model serving) is being built out as containers --
see [`docs/containerisation-plan.md`](docs/containerisation-plan.md).

| Piece | State |
|---|---|
| Section model with mandatory source identity and dates | done |
| Append-only source manifest with checksums | done |
| Sentence-aware chunking, bge-m3 token budget | done |
| CORDIS bulk adapter (Horizon Europe, H2020) | done |
| bge-m3 embedding + throughput benchmark | done |
| PostgreSQL + pgvector schema, hybrid retrieval | not started |
| Reranking and answer composition | not started |
| Containerised stack (Docker Compose, profiles) | in progress |
| PostgreSQL + pgvector container | in progress |
| Containerised ingestion pipeline | not started |
| Model serving: bge-m3, reranker, generation | not started |
| Caddy, Authelia, LLDAP login chain | not started |
| Migration-equivalence proof | not started |

## Requirements

- Python 3.12 (pinned in `.python-version`; the ML wheels do not yet build on 3.13+)
- [`uv`](https://docs.astral.sh/uv/)
- For embedding: an NVIDIA GPU with ~16 GB VRAM and a working CUDA driver

Nothing further needs installing. The runtime stack is containerised, and Docker 29.1.3,
Compose v2.40.3 and the NVIDIA Container Toolkit 1.20.1 are already present on the development
machine. See [`docs/containerisation-plan.md`](docs/containerisation-plan.md) for the tracked
build-out, the pinned image versions and the open risks.

## Setup

Containerised (canonical -- no host packages beyond Docker, which is already present):

```bash
./containers/gen-secrets.sh                # once: writes .env and secrets/, idempotent
docker compose --profile core up -d        # PostgreSQL + pgvector
docker compose run --rm pipeline gcr --help
```

On the host (a dev convenience; the same code, the same results):

```bash
uv sync                  # core pipeline
uv sync --extra embed    # adds torch, transformers, FlagEmbedding (large)
```

## Usage

```bash
uv run gcr fetch horizon          # download CORDIS bulk, record it in the manifest
uv run gcr sections horizon       # build sections, print the corpus profile
uv run gcr sections horizon --out data/interim/horizon.jsonl
uv run gcr benchmark-embed horizon --n 10000
uv run gcr manifest               # show what has been fetched
```

Every command above has a containerised equivalent -- `docker compose run --rm pipeline gcr
sections horizon` and so on -- which is the form used for anything whose result is recorded, so
that measurements are reproducible rather than dependent on the host venv.

`fetch` skips the download when upstream reports an unchanged `Last-Modified`; pass `--force` to
override.

## Tests

```bash
uv run --with pytest pytest              # whole suite
uv run --with pytest pytest -q tests/test_chunking.py
uv run --with pytest pytest -q -k abbreviation      # one test by name
```

The suite needs no network and no GPU: the CORDIS tests build a synthetic zip shaped like the real
one, and chunking falls back to a character-based token estimate when the bge-m3 tokenizer is
absent.

## Repository layout

```
src/gcr/
  models.py          Section, SourceRef, FetchRecord - the sacred fields are required, not optional
  config.py          paths, chunk sizes, corpus caps
  chunking.py        paragraph/sentence splitting and token-budget packing
  fetch.py           downloads that record themselves in the manifest
  manifest.py        append-only JSONL of every payload fetched
  embed.py           bge-m3 loading and the throughput benchmark
  cli.py             the `gcr` command
  sources/cordis.py  CORDIS bulk adapter
data/
  raw/               downloaded payloads (gitignored)
  interim/           built sections (gitignored)
  reference/         source manifest, benchmark results, curated lookups (committed)
```

## Data handling

Payloads are gitignored; the manifest line describing each one is committed, so an ingestion run
can be reproduced from the repository alone. Personal data is dropped at ingestion rather than
later: the CORDIS adapter discards contact forms, street addresses, geolocation, city and VAT
number, keeping organisation names and official organisation URLs only.
