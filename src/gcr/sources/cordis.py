"""CORDIS bulk project adapter.

Upstream publishes one zip per framework programme containing semicolon
delimited CSVs. We use `project.csv` for the text and `organization.csv` for
the coordinator's country and NUTS code, which CLAUDE.md requires as
first-class metadata on every section.

Personal data is dropped at ingestion, not later: `organization.csv` carries
`contactForm`, street address, geolocation and VAT number, and CORDIS
participant records name principal investigators. We keep organisation names
and official organisation URLs only.
"""

from __future__ import annotations

import contextlib
import csv
import io
import sys
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from ..chunking import chunk_text, count_tokens
from ..models import Origin, ProgrammePeriod, Section, SourceRef

# CORDIS objective fields run to a few thousand characters; the default csv
# field cap is smaller than some rows here.
csv.field_size_limit(min(sys.maxsize, 1 << 31 - 1))

SOURCE_SYSTEM = "cordis"
LICENCE = "CC-BY-4.0 (Commission Decision 2011/833/EU)"
ATTRIBUTION = "© European Union, CORDIS"
PROJECT_URL = "https://cordis.europa.eu/project/id/{id}"

DATASETS = {
    "horizon": {
        "url": "https://cordis.europa.eu/data/cordis-HORIZONprojects-csv.zip",
        "programme": "HORIZON",
        "period": ProgrammePeriod.P2021_2027,
    },
    "h2020": {
        "url": "https://cordis.europa.eu/data/cordis-h2020projects-csv.zip",
        "programme": "H2020",
        "period": ProgrammePeriod.P2014_2020,
    },
}

# Columns in organization.csv that identify or locate a person. Dropped before
# anything downstream can see them.
_ORG_PII_COLUMNS = frozenset(
    {"contactForm", "street", "postCode", "geolocation", "vatNumber", "city"}
)


@dataclass(frozen=True)
class Coordinator:
    """The coordinating organisation, reduced to the non-personal fields."""

    name: str | None
    country: str | None
    nuts_code: str | None
    url: str | None
    is_sme: bool


def _open_csv(zf: zipfile.ZipFile, name: str) -> Iterator[dict[str, str]]:
    with zf.open(name) as raw:
        text = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
        yield from csv.DictReader(text, delimiter=";")


def _parse_date(value: str | None) -> date | None:
    """CORDIS mixes plain dates and timestamps; both appear in one column."""
    if not value:
        return None
    v = value.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            # Naive on purpose: upstream states no zone and we keep only the
            # calendar date, which is what a citation's "as of" line shows.
            return datetime.strptime(v, fmt).date()  # noqa: DTZ007
        except ValueError:
            continue
    return None


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    v = value.strip()
    return v or None


def load_coordinators(zip_path: Path) -> dict[str, Coordinator]:
    """Map projectID -> coordinating organisation, PII columns discarded.

    Falls back to the first listed participant when a project has no row marked
    `coordinator`, so country is populated wherever upstream allows.
    """
    coordinators: dict[str, Coordinator] = {}
    fallbacks: dict[str, Coordinator] = {}

    with zipfile.ZipFile(zip_path) as zf:
        for raw_row in _open_csv(zf, "organization.csv"):
            row = {k: v for k, v in raw_row.items() if k not in _ORG_PII_COLUMNS}
            pid = _clean(row.get("projectID"))
            if not pid:
                continue
            country = _clean(row.get("country"))
            org = Coordinator(
                name=_clean(row.get("name")),
                country=country.upper() if country and len(country) == 2 else None,
                nuts_code=_clean(row.get("nutsCode")),
                url=_clean(row.get("organizationURL")),
                is_sme=(row.get("SME") or "").strip().lower() == "true",
            )
            if (row.get("role") or "").strip().lower() == "coordinator":
                coordinators.setdefault(pid, org)
            else:
                fallbacks.setdefault(pid, org)

    for pid, org in fallbacks.items():
        coordinators.setdefault(pid, org)
    return coordinators


def _metadata_sentence(row: dict[str, str], coord: Coordinator | None, programme: str) -> str:
    """An English sentence built by our own code from structured fields.

    Marked GENERATED_FROM_STRUCTURED, not ENGLISH_ORIGIN: it is not upstream
    prose. This is the same technique the report prescribes for Kohesio, and it
    makes the numbers and dates retrievable by keyword search.
    """
    parts: list[str] = []
    title = _clean(row.get("title"))
    acronym = _clean(row.get("acronym"))
    pid = _clean(row.get("id"))

    head = f"{programme} project {acronym or pid}"
    if title:
        head += f', "{title}"'
    parts.append(head + ".")

    if (scheme := _clean(row.get("fundingScheme"))) :
        parts.append(f"Funding scheme: {scheme}.")
    if (topic := _clean(row.get("topics"))) :
        parts.append(f"Call topic: {topic}.")
    if (call := _clean(row.get("masterCall"))) :
        parts.append(f"Master call: {call}.")

    start, end = _clean(row.get("startDate")), _clean(row.get("endDate"))
    if start and end:
        parts.append(f"Runs from {start} to {end}.")

    # CORDIS writes money with a comma decimal separator.
    contrib = (_clean(row.get("ecMaxContribution")) or "").replace(",", ".")
    if contrib:
        with contextlib.suppress(ValueError):
            parts.append(f"Maximum EU contribution: EUR {float(contrib):,.2f}.")

    if (status := _clean(row.get("status"))) :
        parts.append(f"Status: {status.lower()}.")
    if coord and coord.name:
        where = f" in {coord.country}" if coord.country else ""
        sme = " (an SME)" if coord.is_sme else ""
        parts.append(f"Coordinated by {coord.name}{sme}{where}.")
    if (kw := _clean(row.get("keywords"))) :
        parts.append(f"Keywords: {kw}.")

    return " ".join(parts)


def iter_sections(
    zip_path: Path,
    dataset: str = "horizon",
    fetch_date: datetime | None = None,
    limit: int | None = None,
) -> Iterator[Section]:
    """Yield sections for every project in the dataset.

    Section 0 is the generated metadata sentence; sections 1..n are chunks of
    the upstream `objective` text.
    """
    spec = DATASETS[dataset]
    programme, period = str(spec["programme"]), spec["period"]
    assert isinstance(period, ProgrammePeriod)
    fetched = fetch_date or datetime.now(UTC)

    coordinators = load_coordinators(zip_path)

    with zipfile.ZipFile(zip_path) as zf:
        for i, row in enumerate(_open_csv(zf, "project.csv")):
            if limit is not None and i >= limit:
                break
            pid = _clean(row.get("id"))
            if not pid:
                continue

            coord = coordinators.get(pid)
            source = SourceRef(
                source_system=SOURCE_SYSTEM,
                source_id=pid,
                source_url=PROJECT_URL.format(id=pid),
                source_date=_parse_date(row.get("contentUpdateDate")),
                fetch_date=fetched,
                licence=LICENCE,
                attribution=ATTRIBUTION,
            )
            common = {
                "source": source,
                "country": coord.country if coord else None,
                "nuts_code": coord.nuts_code if coord else None,
                "programme": programme,
                "programme_period": period,
            }

            ordinal = 0
            meta = _metadata_sentence(row, coord, programme)
            if meta.strip():
                yield Section(
                    section_id=f"{SOURCE_SYSTEM}:{pid}:{ordinal}",
                    text=meta,
                    origin=Origin.GENERATED_FROM_STRUCTURED,
                    part="metadata",
                    ordinal=ordinal,
                    token_count=count_tokens(meta),
                    **common,
                )
                ordinal += 1

            for chunk in chunk_text(_clean(row.get("objective")) or ""):
                yield Section(
                    section_id=f"{SOURCE_SYSTEM}:{pid}:{ordinal}",
                    text=chunk,
                    origin=Origin.ENGLISH_ORIGIN,
                    part="objective",
                    ordinal=ordinal,
                    token_count=count_tokens(chunk),
                    **common,
                )
                ordinal += 1
