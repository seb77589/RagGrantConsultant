"""`fetch_date` on a section must be when the source was fetched.

Found by the host/container parity gate: the two runs produced identical
section IDs and identical text for all 50,940 rows, but differing fetch_date on
every one -- because `gcr sections` let it default to `datetime.now(UTC)`, the
time the sections were built.

That matters beyond tidiness. CLAUDE.md makes fetch date sacred because it
drives "as of" dates and staleness warnings, and a corpus rebuilt today from a
two-year-old download would have reported itself as fresh.
"""

from __future__ import annotations

import zipfile
from datetime import UTC, datetime
from pathlib import Path

from gcr.sources import cordis

_FETCHED = datetime(2026, 9, 30, 21, 20, 3, tzinfo=UTC)


def _minimal_zip(tmp_path: Path) -> Path:
    """A zip shaped like the real CORDIS bulk download, with one project."""
    path = tmp_path / "cordis-HORIZONprojects-csv.zip"
    project = (
        "id;acronym;status;title;startDate;endDate;totalCost;ecMaxContribution;"
        "legalBasis;topics;frameworkProgramme;masterCall;subCall;fundingScheme;"
        "nature;objective;contentUpdateDate;rcn;grantDoi\n"
        "101;ACME;SIGNED;A title;2026-01-01;2027-01-01;100;100;HORIZON;TOPIC-1;"
        "HORIZON;CALL;SUBCALL;HORIZON-RIA;;An objective sentence.;2026-09-22;1;doi\n"
    )
    organization = (
        "projectID;projectAcronym;organisationID;vatNumber;name;shortName;SME;"
        "activityType;street;postCode;city;country;nutsCode;geolocation;"
        "organizationURL;contactForm;order;role;ecContribution;netEcContribution;"
        "totalCost;endOfParticipation;active\n"
        "101;ACME;1;;Acme Research;ACME;false;REC;;;Dublin;IE;IE061;;https://acme.ie;;1;"
        "coordinator;100;100;100;false;true\n"
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("project.csv", project)
        zf.writestr("organization.csv", organization)
    return path


def test_explicit_fetch_date_is_carried_onto_every_section(tmp_path: Path) -> None:
    zip_path = _minimal_zip(tmp_path)
    sections = list(cordis.iter_sections(zip_path, dataset="horizon", fetch_date=_FETCHED))
    assert sections, "fixture produced no sections"
    assert all(s.source.fetch_date == _FETCHED for s in sections)


def test_without_one_it_falls_back_to_now(tmp_path: Path) -> None:
    """The fallback stays: with no manifest record, the honest answer is 'now',
    not a fabricated earlier date."""
    before = datetime.now(UTC)
    sections = list(cordis.iter_sections(_minimal_zip(tmp_path), dataset="horizon"))
    assert all(s.source.fetch_date >= before for s in sections)


def test_fetch_date_is_stable_across_runs(tmp_path: Path) -> None:
    """Two builds of the same source must agree, or the migration-equivalence
    comparison is noisy for a reason that has nothing to do with migrating."""
    zip_path = _minimal_zip(tmp_path)
    first = list(cordis.iter_sections(zip_path, dataset="horizon", fetch_date=_FETCHED))
    second = list(cordis.iter_sections(zip_path, dataset="horizon", fetch_date=_FETCHED))
    assert [s.model_dump_json() for s in first] == [s.model_dump_json() for s in second]
