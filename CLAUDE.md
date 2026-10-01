# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current state

Phase 1, early. The ingestion pipeline works end to end for CORDIS; none of the runtime stack is
built yet. The design below comes from
`compass_artifact_wf-74a0c4d9-b271-53b8-93db-67162cf90f3f_text_markdown.md`, the feasibility
report, which remains the design record. Where measurement has since contradicted it,
`docs/measurements.md` wins — see "Scale and hardware constraints".

```bash
uv sync                          # core pipeline (Python 3.12, pinned: ML wheels lack 3.13+)
uv sync --extra embed            # adds torch, transformers, FlagEmbedding (large)

uv run gcr fetch horizon         # download CORDIS bulk, record it in the source manifest
uv run gcr sections horizon      # build sections, print the corpus profile
uv run gcr benchmark-embed horizon --n 10000
uv run gcr manifest              # show what has been fetched

uv run --with pytest pytest                     # whole suite; no network, no GPU needed
uv run --with pytest pytest -q -k abbreviation  # one test by name
uv run --with ruff ruff check src tests         # lint set is pinned in pyproject.toml
```

The containerised path is the canonical one — the host venv above stays as a dev convenience:

```bash
./containers/gen-secrets.sh                     # once: writes .env and secrets/ (idempotent)
docker compose --profile core up -d             # PostgreSQL + pgvector
docker compose run --rm pipeline gcr sections horizon
docker compose run --rm pipeline gcr ask "..."       # needs the models profile
docker compose run --rm pipeline pytest
docker compose --profile core --profile models --profile auth --profile edge up -d
```

**Nothing needs installing on the development machine.** Docker 29.1.3, Compose v2.40.3 and the
NVIDIA Container Toolkit 1.20.1 are already present, and every other service — PostgreSQL+pgvector,
Caddy, Authelia, LLDAP, the model servers — runs as a container. The ingestion pipeline is
containerised too, so `torch`/`transformers`/`FlagEmbedding` need not be on the host either.
`docs/containerisation-plan.md` is the tracked, resumable checklist for the build-out; it also
records the pinned image versions and the open risks.

## What is being built

A retrieval-augmented question-answering system that acts as a grant consultant for European
companies. Corpus: **English-origin documents only**, European-level funding sources first
(EUR-Lex/CELLAR, Funding & Tenders Portal search API, CORDIS, Cohesion Open Data, Kohesio,
keep.eu, Eureka/Eurostars), plus national sources from the handful of countries that publish
funding information in English (Ireland, Malta, Estonia, Finland, Denmark; later Cyprus, Norway,
Switzerland and partial-English publishers).

It doubles as a rehearsal for a specific freelance job, so the job-relevant parts of the stack are
not optional: hybrid retrieval in PostgreSQL/pgvector, answers with sources, group-based access
restriction, and a **migration-equivalence proof** (fixed question set; compare retrieved
identifiers, rank overlap and answer similarity before and after a dump/restore to a new data
centre).

## Planned architecture

Runtime, per the report's work packages:

- **Docker Compose with profiles** for all services (`core`, `tools`, `models`, `auth`, `edge`).
  This supersedes the report's "rootless Podman with Quadlet systemd units": the engine, Compose and
  the NVIDIA Container Toolkit were already installed on this machine, so Docker keeps the host clean
  at zero cost, where Podman would have meant installing five packages. The trade is real and worth
  knowing — it drops the 8–12 h Quadlet work package the report counted as job practice. Compose
  files avoid Docker-only features where that is free; the one exception is the GPU `driver: cdi`
  reservation block, which podman-compose does not support.
- **Caddy** reverse proxy in front of **Authelia** + **LLDAP** for login; Authelia/LLDAP groups map
  to row-level filters in the database.
- **PostgreSQL + pgvector**: HNSW vector index alongside PostgreSQL full-text search.
- **Model serving behind one OpenAI-compatible endpoint**: Qwen3.5-9B at 4-bit for generation,
  `bge-m3` for embeddings (1024 dimensions), `bge-reranker-v2-m3` for reranking.
- **Pipelines**: ingestion → chunking → embedding; then retrieval → rerank → answer with sources.
  The answer half lives in `src/gcr/{services,retrieve,figures,answer,api}.py`: `retrieve` adds
  reranking on top of `db.search_hybrid`, `answer` composes and cites, and `figures` enforces the
  no-hallucinated-figures rule in code rather than trusting the prompt.

Retrieval path: structured eligibility filter (country, NUTS region, company size, NACE sector,
programme, status, deadline) → hybrid keyword + vector search → merge → rerank → 6–10 sections into
the generation context.

## Hard design rules

These come from the report's recommendations and are the decisions most likely to be silently
broken by new code:

- **Source identity and dates are sacred.** Every section stores its source identifier (CELEX
  number for legislation, topic identifier for calls, CORDIS project number), source date, and
  fetch date. These drive citations, "as of" dates, staleness warnings, and the migration
  comparison — nothing may be ingested without them.
- **Country and NUTS region are first-class metadata on every section**, not derived at query time.
- **Add a programme-period field from day one** (2021–2027, 2028–2034) so the successor framework
  programmes can coexist with the current ones without a schema redesign.
- **Eligibility is rules in code, not model reasoning.** SME status (Recommendation 2003/361),
  de minimis headroom (€300,000 per undertaking over three years, Regulation 2023/2831), and
  regional aid ceilings are computed by code; the model only explains the computed result, with
  sources.
- **No hallucinated figures.** Refuse to state amounts, funding rates, or deadlines that are not
  present in the retrieved text; show the supporting quote; flag stale documents. Enforced by
  `gcr.figures.unsupported`, which compares *normalised* values so that "EUR 12 million" against a
  source saying "EUR 12,000,000" counts as quoted, not invented. The prompt asks; the check enforces.
  Two limits are deliberate and documented: a coincidentally-present number passes, and a false claim
  made in words carries no figure to check.
- **Keep Kohesio's machine-translated text out of the core corpus.** Kohesio English is eTranslation
  output, which breaks the English-origin rule. Use its structured fields (numbers, codes, regions)
  and generate English sentences from them. Any translated tier lives in a separate table and index,
  is labelled in answers, and is access-restricted.
- **Strip person-level data at ingestion**: National Contact Point names, CORDIS participant contacts
  and principal investigators, Digital Innovation Hub contact persons, Enterprise Europe Network
  profile contacts, and Kohesio beneficiaries who are private individuals. Keep organisation names
  and official organisation URLs.
- **Attribution and disclaimer.** Credit "© European Union" with the source link on every cited
  source and on an "About the data" page, and indicate that text was chunked/extracted/summarised.
  Do not use the Commission logo or emblem. Ship the independence disclaimer (report section F).
  For non-Commission sources (keep.eu, Eureka, European Investment Fund), link out and quote
  briefly until their terms are confirmed.

## Scale and hardware constraints

Actual machine: RTX 3080 Laptop (15.6 GB usable VRAM), 61 GB system RAM, **385 GB free disk —
not the ~8 TB the report assumed**, so raw corpus, weights and snapshots need managing.

Measured, superseding the report's estimates (full numbers and caveats in `docs/measurements.md`):

- **bge-m3 embeds at ~141 sections/s at 1.42 GB peak VRAM**, batch 32. Throughput is flat from
  batch 16 to 64 and falls off at 128: the card is compute-bound, not batch-bound.
- That puts 500,000 sections at about **1 hour**, against the report's 5–13 h. Re-embedding after a
  chunking change is therefore roughly an hour, not a day — chunking is far less expensive to
  reverse than planned, though still versioned via `CHUNKING_VERSION`.
- **The 500,000-section core cap was justified partly by embedding cost, so that justification is
  now weak.** Do not treat the cap as settled; revisit it once HNSW build time and search latency
  are measured, which needs PostgreSQL and pgvector installed.
- 1.42 GB peak VRAM against 15.6 GB available means the generation model can likely stay resident
  during bulk embedding, contrary to the report's advice to stop it. Not yet verified with Qwen
  loaded alongside.
- Still unmeasured and still to be respected: Qwen at 4-bit with context capped at 16k–32k tokens
  (never the full 262k — reranked retrieval needs only 6–10 sections), thermal throttling on
  multi-hour runs, HNSW build time, and search latency.
- Always measure token counts with the real bge-m3 tokenizer. The character heuristic used as a
  fallback over-estimates by about 17%, which inflates section counts and causes needless splits.

## Phasing

Phase 1 (~130–210 h) is the job rehearsal: European level plus the five fully-English national
publishers, every stack item exercised, ~150-question evaluation set, migration-equivalence proof on
a frozen snapshot. Phase 2 (~210–340 h cumulative) adds all-country coverage, the link-out registry
of national authorities, regional aid intensities, programme association status, Eurostars national
rules, application checklists, and a 300+ question per-country evaluation set.

Corpus sizing has already moved: CORDIS Horizon Europe alone yields 50,940 sections from 23,613
projects, and H2020 should add roughly 75,000. That is about 126,000 against the report's central
estimate of 80,000 for both datasets combined, so CORDIS is a larger share of the corpus than
planned.
