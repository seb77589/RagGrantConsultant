# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current state

There is no code, build system, or test suite in this repository yet. The only file is
`compass_artifact_wf-74a0c4d9-b271-53b8-93db-67162cf90f3f_text_markdown.md`, a feasibility and
analysis report for the planned system. Everything below is distilled from that report — it is the
design that new code is expected to follow, not a description of existing code. Update this file
with real commands as soon as a build, test, or run path exists.

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

- **Rootless Podman** with Quadlet systemd units for all services.
- **Caddy** reverse proxy in front of **Authelia** + **LLDAP** for login; Authelia/LLDAP groups map
  to row-level filters in the database.
- **PostgreSQL + pgvector**: HNSW vector index alongside PostgreSQL full-text search.
- **Model serving behind one OpenAI-compatible endpoint**: Qwen3.5-9B at 4-bit for generation,
  `bge-m3` for embeddings (1024 dimensions), `bge-reranker-v2-m3` for reranking.
- **Pipelines**: ingestion → chunking → embedding; then retrieval → rerank → answer with sources.

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
  present in the retrieved text; show the supporting quote; flag stale documents.
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

Target laptop: 16 GB GPU memory, 64 GB system memory, ~8 TB SSD.

- **Cap the core corpus at about 500,000 sections**; Phase 1 targets 300,000–400,000. Use
  half-precision vectors above 500,000.
- Model footprint at 4-bit with context capped at 16k–32k tokens is roughly 9–12 GB of the 16 GB
  available. Do not run with Qwen's full 262k context — reranked retrieval needs only 6–10 sections.
- The GPU cannot embed and generate at full speed simultaneously. Run bulk embedding with the chat
  model stopped, or overnight; expect thermal throttling on long runs.
- Re-embedding after a chunking change is the real cost (a full day at 1M sections), so treat
  chunking decisions as expensive to reverse.
- Measure actual throughput on 10,000 sections before committing to any of the report's estimates.

## Phasing

Phase 1 (~130–210 h) is the job rehearsal: European level plus the five fully-English national
publishers, every stack item exercised, ~150-question evaluation set, migration-equivalence proof on
a frozen snapshot. Phase 2 (~210–340 h cumulative) adds all-country coverage, the link-out registry
of national authorities, regional aid intensities, programme association status, Eurostars national
rules, application checklists, and a 300+ question per-country evaluation set.
