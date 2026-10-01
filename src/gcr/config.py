"""Paths and tunables.

Values that the report calls out as expensive to reverse (chunk size) or as
hardware caps (corpus ceiling) live here so they are visible in one place and
in the manifest of any run.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

DATA_RAW = REPO_ROOT / "data" / "raw"
DATA_INTERIM = REPO_ROOT / "data" / "interim"
DATA_PROCESSED = REPO_ROOT / "data" / "processed"
DATA_REFERENCE = REPO_ROOT / "data" / "reference"
MANIFEST_PATH = DATA_REFERENCE / "source_manifest.jsonl"

# Chunking. bge-m3 accepts 8192 tokens, but the report sizes the corpus at
# ~400 tokens per section and the answer context at 6-10 sections, so keep
# sections small. Re-embedding after a change here costs about a day at 1M
# sections: treat it as a versioned decision, not a free knob.
TARGET_TOKENS = 400
MAX_TOKENS = 512
OVERLAP_TOKENS = 50
CHUNKING_VERSION = "v1"

# Embedding. Batch 32 measured as the plateau on an RTX 3080 Laptop: throughput
# is flat from 16 to 64 and falls off at 128, so the card is compute-bound
# rather than batch-bound. See docs/measurements.md.
EMBED_MODEL = "BAAI/bge-m3"
EMBED_DIM = 1024
EMBED_BATCH_SIZE = 32

# Hardware ceilings from the report's section E, on a 16 GB laptop GPU.
CORE_SECTION_CAP = 500_000
PHASE1_SECTION_TARGET = 400_000

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
# These four are the only environment variables in the codebase, and they share
# one justification: each names *where something is*, which genuinely differs
# between running inside the compose network and running from the host against
# the ports compose publishes. Everything else in this file is a decision rather
# than a deployment detail and belongs in version control.
#
# (An earlier version of this comment claimed DATABASE_URL was the only
# environment variable "deliberately". The reasoning was about the category of
# value, not the count, and three service endpoints fall in the same category.)
#
# The defaults target the host's view, so a host-side `uv run` works with no
# setup; compose overrides each with its in-network form.

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://gcr@127.0.0.1:5432/gcr",
)

# Text Embeddings Inference listens on port 80 inside its container, not 8080.
# Query embeddings come from here rather than from an in-process model: it keeps
# the index and the query encoder provably the same weights (measured agreement
# with the local path is cosine 0.999988) and lets the CLI run on the small
# image with no GPU.
TEI_EMBED_URL = os.environ.get("TEI_EMBED_URL", "http://127.0.0.1:8081")
# Reranking is TEI-native at /rerank; there is no OpenAI-compatible route.
TEI_RERANK_URL = os.environ.get("TEI_RERANK_URL", "http://127.0.0.1:8082")
# llama.cpp, OpenAI-compatible at /v1/chat/completions.
LLM_URL = os.environ.get("LLM_URL", "http://127.0.0.1:8083")

# ---------------------------------------------------------------------------
# Retrieval and answering
# ---------------------------------------------------------------------------

# Candidates drawn from each half of the hybrid search before reranking. The
# reranker is the expensive, accurate step and the merge is the cheap, rough
# one, so it pays to be generous here and strict afterwards.
RETRIEVE_CANDIDATES = 50
# Sections that reach the generation context. The report is explicit that
# reranked retrieval needs only 6-10, which is also why the model's context is
# capped far below its native window.
RERANK_TOP_K = 8

# A source whose upstream date is older than this is flagged in the answer.
# Eighteen months: long enough that annual calls are not permanently stale,
# short enough to catch a superseded de minimis ceiling. Note this is
# source_date, not fetch_date -- a corpus rebuilt today from an old download is
# still old.
STALE_AFTER_DAYS = 548

# Generation. Low temperature because the task is quoting retrieved text, not
# writing prose; max_tokens bounded so a runaway answer cannot push latency out.
LLM_TEMPERATURE = 0.2
LLM_MAX_TOKENS = 800

# Table names, so the two tiers cannot be confused in a query. The translated
# tier is separate per CLAUDE.md: it is labelled in answers and
# access-restricted, and must never be merged into the core corpus.
SECTIONS_TABLE = "sections"
SECTIONS_TRANSLATED_TABLE = "sections_translated"


def ensure_dirs() -> None:
    for p in (DATA_RAW, DATA_INTERIM, DATA_PROCESSED, DATA_REFERENCE):
        p.mkdir(parents=True, exist_ok=True)
