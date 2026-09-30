"""Downloading with manifest recording.

Every payload that lands in data/raw is checksummed and written to the source
manifest. The payload is gitignored; the manifest line is committed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx

from .config import REPO_ROOT
from .manifest import append, latest_for, sha256_file
from .models import FetchRecord


def download(
    url: str,
    dest: Path,
    source_system: str,
    licence: str,
    attribution: str,
    *,
    force: bool = False,
    note: str | None = None,
    timeout: float = 300.0,
) -> FetchRecord:
    """Fetch `url` to `dest`, recording identity and checksum in the manifest.

    Skips the download when the file already exists and upstream reports the
    same Last-Modified as the previous recorded fetch, unless `force`.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    previous = latest_for(source_system, url)

    upstream_lm: str | None = None
    with httpx.Client(follow_redirects=True, timeout=timeout) as client:
        try:
            head = client.head(url)
            upstream_lm = head.headers.get("last-modified")
        except httpx.HTTPError:
            upstream_lm = None

        unchanged = (
            not force
            and dest.exists()
            and previous is not None
            and upstream_lm is not None
            and previous.upstream_last_modified == upstream_lm
        )
        if unchanged:
            assert previous is not None
            return previous

        with client.stream("GET", url) as response:
            response.raise_for_status()
            tmp = dest.with_suffix(dest.suffix + ".part")
            with tmp.open("wb") as f:
                for block in response.iter_bytes(chunk_size=1 << 20):
                    f.write(block)
            tmp.replace(dest)
            upstream_lm = response.headers.get("last-modified", upstream_lm)

    record = FetchRecord(
        source_system=source_system,
        url=url,
        path=str(dest.relative_to(REPO_ROOT)),
        sha256=sha256_file(dest),
        bytes=dest.stat().st_size,
        fetch_date=datetime.now(UTC),
        upstream_last_modified=upstream_lm,
        licence=licence,
        attribution=attribution,
        note=note,
    )
    append(record)
    return record
