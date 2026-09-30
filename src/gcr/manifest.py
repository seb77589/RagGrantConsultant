"""Append-only source manifest.

One JSON object per line, committed to git. Records identity, checksum and
dates for every payload fetched, so an ingestion run can be reproduced and the
before/after migration comparison has something stable to compare against.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .config import MANIFEST_PATH
from .models import FetchRecord


def sha256_file(path: Path, chunk_bytes: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while block := f.read(chunk_bytes):
            h.update(block)
    return h.hexdigest()


def append(record: FetchRecord, manifest_path: Path = MANIFEST_PATH) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    line = record.model_dump_json()
    with manifest_path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def read_all(manifest_path: Path = MANIFEST_PATH) -> list[FetchRecord]:
    if not manifest_path.exists():
        return []
    out: list[FetchRecord] = []
    with manifest_path.open(encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if line:
                out.append(FetchRecord.model_validate(json.loads(line)))
    return out


def latest_for(
    source_system: str, url: str, manifest_path: Path = MANIFEST_PATH
) -> FetchRecord | None:
    """Most recent fetch of a given URL, used to skip redundant downloads."""
    matches = [
        r for r in read_all(manifest_path) if r.source_system == source_system and r.url == url
    ]
    return max(matches, key=lambda r: r.fetch_date) if matches else None
