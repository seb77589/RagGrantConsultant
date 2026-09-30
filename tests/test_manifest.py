from datetime import UTC, datetime
from pathlib import Path

from gcr import manifest
from gcr.models import FetchRecord


def _rec(**over):
    base = {
        "source_system": "cordis",
        "url": "https://cordis.europa.eu/data/x.zip",
        "path": "data/raw/cordis/x.zip",
        "sha256": "a" * 64,
        "bytes": 123,
        "fetch_date": datetime(2026, 10, 1, tzinfo=UTC),
        "licence": "CC-BY-4.0",
        "attribution": "© European Union",
    }
    return FetchRecord(**(base | over))


def test_append_and_read_roundtrip(tmp_path: Path):
    p = tmp_path / "m.jsonl"
    manifest.append(_rec(), p)
    manifest.append(_rec(sha256="b" * 64), p)
    records = manifest.read_all(p)
    assert [r.sha256[0] for r in records] == ["a", "b"]


def test_read_all_on_missing_file_is_empty(tmp_path: Path):
    assert manifest.read_all(tmp_path / "absent.jsonl") == []


def test_latest_for_returns_most_recent_fetch(tmp_path: Path):
    p = tmp_path / "m.jsonl"
    manifest.append(_rec(fetch_date=datetime(2026, 1, 1, tzinfo=UTC), sha256="a" * 64), p)
    manifest.append(_rec(fetch_date=datetime(2026, 9, 1, tzinfo=UTC), sha256="c" * 64), p)
    manifest.append(_rec(url="https://other", sha256="d" * 64), p)
    latest = manifest.latest_for("cordis", "https://cordis.europa.eu/data/x.zip", p)
    assert latest is not None and latest.sha256[0] == "c"


def test_sha256_file_matches_known_digest(tmp_path: Path):
    f = tmp_path / "f.bin"
    f.write_bytes(b"abc")
    assert manifest.sha256_file(f) == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )
