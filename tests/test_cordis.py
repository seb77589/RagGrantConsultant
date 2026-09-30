"""CORDIS adapter tests against a synthetic zip shaped like the real one."""

import csv
import io
import zipfile
from pathlib import Path

import pytest

from gcr.models import Origin, ProgrammePeriod
from gcr.sources import cordis

PROJECT_COLS = [
    "id", "acronym", "status", "title", "startDate", "endDate", "totalCost",
    "ecMaxContribution", "topics", "ecSignatureDate", "frameworkProgramme",
    "masterCall", "subCall", "fundingScheme", "nature", "objective",
    "contentUpdateDate", "rcn", "grantDoi", "keywords", "Human-validated",
    "legalBasis",
]
ORG_COLS = [
    "projectID", "projectAcronym", "organisationID", "vatNumber", "name",
    "shortName", "SME", "activityType", "street", "postCode", "city",
    "country", "nutsCode", "geolocation", "organizationURL", "contactForm",
    "contentUpdateDate", "rcn", "order", "role", "ecContribution",
    "netEcContribution", "totalCost", "endOfParticipation", "active",
]


def _csv_bytes(cols, rows):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, delimiter=";")
    w.writeheader()
    for r in rows:
        w.writerow({c: r.get(c, "") for c in cols})
    return buf.getvalue().encode("utf-8")


@pytest.fixture
def fake_zip(tmp_path: Path) -> Path:
    projects = [
        {
            "id": "101069359",
            "acronym": "SolDAC",
            "title": "Full spectrum SOLar Direct Air Capture",
            "status": "SIGNED",
            "startDate": "2022-09-01",
            "endDate": "2025-08-31",
            "ecMaxContribution": "2073781,25",
            "topics": "HORIZON-CL5-2021-D2-01-11",
            "masterCall": "HORIZON-CL5-2021-D2-01",
            "fundingScheme": "HORIZON-RIA",
            "objective": "Ethylene is the primary building block. SolDAC proves a breakthrough.",
            "contentUpdateDate": "2026-03-27 15:10:23",
            "keywords": "solar energy, direct air capture",
        },
        {
            "id": "999",
            "acronym": "NODATE",
            "title": "Project without an update date",
            "status": "CLOSED",
            "objective": "A short objective.",
            "contentUpdateDate": "",
        },
    ]
    orgs = [
        # Deliberately a non-coordinator listed first, to check role handling.
        {"projectID": "101069359", "name": "Partner Ltd", "country": "IE",
         "nutsCode": "IE05", "role": "participant", "SME": "true",
         "contactForm": "https://example.org/contact", "street": "1 Main St",
         "vatNumber": "IE1234567X", "geolocation": "53.3,-6.2", "city": "Dublin"},
        {"projectID": "101069359", "name": "Coordinator SA", "country": "el",
         "nutsCode": "EL30", "role": "coordinator", "SME": "false",
         "organizationURL": "https://coord.example.org",
         "contactForm": "https://example.org/contact2", "street": "2 Side St"},
        # Project 999 has no coordinator row at all.
        {"projectID": "999", "name": "Only Participant", "country": "MT",
         "nutsCode": "MT00", "role": "participant", "SME": "true"},
    ]
    path = tmp_path / "cordis-test.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("project.csv", _csv_bytes(PROJECT_COLS, projects))
        zf.writestr("organization.csv", _csv_bytes(ORG_COLS, orgs))
    return path


def test_coordinator_is_preferred_over_participant(fake_zip):
    coords = cordis.load_coordinators(fake_zip)
    assert coords["101069359"].name == "Coordinator SA"
    assert coords["101069359"].country == "EL"  # normalised from "el"


def test_first_participant_is_used_when_no_coordinator_row(fake_zip):
    coords = cordis.load_coordinators(fake_zip)
    assert coords["999"].name == "Only Participant"
    assert coords["999"].country == "MT"


def test_personal_and_location_fields_are_dropped(fake_zip):
    """Coordinator carries no contact, address, geolocation or VAT field."""
    coord = cordis.load_coordinators(fake_zip)["101069359"]
    leaked = [
        v for v in vars(coord).values()
        if isinstance(v, str) and (
            "contact" in v.lower() or "Side St" in v or "IE1234567X" in v or "53.3" in v
        )
    ]
    assert leaked == []
    assert set(vars(coord)) == {"name", "country", "nuts_code", "url", "is_sme"}


def test_sections_carry_identity_and_country(fake_zip):
    sections = list(cordis.iter_sections(fake_zip, dataset="horizon"))
    assert sections, "expected sections"
    for s in sections:
        assert s.source.source_system == "cordis"
        assert s.source.source_id
        assert s.source.source_url.startswith("https://cordis.europa.eu/project/id/")
        assert s.source.fetch_date is not None
        assert s.programme == "HORIZON"
        assert s.programme_period is ProgrammePeriod.P2021_2027
        assert s.country is not None


def test_first_section_is_generated_metadata_then_objective(fake_zip):
    sections = [s for s in cordis.iter_sections(fake_zip) if s.source.source_id == "101069359"]
    assert sections[0].origin is Origin.GENERATED_FROM_STRUCTURED
    assert sections[0].part == "metadata"
    assert all(s.origin is Origin.ENGLISH_ORIGIN for s in sections[1:])
    assert all(s.part == "objective" for s in sections[1:])


def test_metadata_sentence_formats_money_and_topic(fake_zip):
    meta = next(iter(cordis.iter_sections(fake_zip))).text
    # CORDIS writes "2073781,25" with a comma decimal separator.
    assert "EUR 2,073,781.25" in meta
    assert "HORIZON-CL5-2021-D2-01-11" in meta
    assert "Coordinated by Coordinator SA" in meta
    assert "in EL" in meta


def test_section_ids_are_stable_and_unique(fake_zip):
    ids = [s.section_id for s in cordis.iter_sections(fake_zip)]
    assert len(ids) == len(set(ids))
    assert ids[0] == "cordis:101069359:0"


def test_missing_update_date_becomes_none_not_a_guess(fake_zip):
    s = next(s for s in cordis.iter_sections(fake_zip) if s.source.source_id == "999")
    assert s.source.source_date is None


def test_limit_counts_projects_not_sections(fake_zip):
    sections = list(cordis.iter_sections(fake_zip, limit=1))
    assert {s.source.source_id for s in sections} == {"101069359"}
