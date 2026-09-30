"""Paths and tunables.

Values that the report calls out as expensive to reverse (chunk size) or as
hardware caps (corpus ceiling) live here so they are visible in one place and
in the manifest of any run.
"""

from __future__ import annotations

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


def ensure_dirs() -> None:
    for p in (DATA_RAW, DATA_INTERIM, DATA_PROCESSED, DATA_REFERENCE):
        p.mkdir(parents=True, exist_ok=True)
