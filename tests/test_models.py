from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from gcr.models import Origin, ProgrammePeriod, Section, SourceRef


def _source(**over):
    base = {
        "source_system": "cordis",
        "source_id": "101069359",
        "source_url": "https://cordis.europa.eu/project/id/101069359",
        "source_date": date(2026, 3, 27),
        "fetch_date": datetime(2026, 10, 1, tzinfo=UTC),
        "licence": "CC-BY-4.0",
        "attribution": "© European Union, CORDIS",
    }
    return SourceRef(**(base | over))


def _section(**over):
    base = {
        "section_id": "cordis:101069359:0",
        "source": _source(),
        "text": "Ethylene is the chemical industry's primary building block.",
        "origin": Origin.ENGLISH_ORIGIN,
        "ordinal": 0,
        "token_count": 11,
    }
    return Section(**(base | over))


def test_country_is_normalised_to_upper_iso2():
    assert _section(country="el").country == "EL"


def test_invalid_country_is_rejected():
    with pytest.raises(ValidationError):
        _section(country="GRC")


def test_blank_text_is_rejected():
    # A blank section is uncitable, so it must never be constructible.
    with pytest.raises(ValidationError):
        _section(text="   ")


def test_source_identity_fields_are_required():
    # CLAUDE.md: identity and dates are sacred. Omitting one must fail loudly
    # at construction, not silently produce an unattributable section.
    for missing in ("source_id", "source_url", "licence", "attribution"):
        with pytest.raises(ValidationError):
            _source(**{missing: ""})


def test_source_date_may_be_absent_but_must_be_explicit():
    # 389 CORDIS rows genuinely publish no update date; None is allowed, but
    # the field cannot be skipped.
    assert _source(source_date=None).source_date is None
    with pytest.raises(ValidationError):
        SourceRef(
            source_system="cordis",
            source_id="1",
            source_url="u",
            fetch_date=datetime(2026, 10, 1, tzinfo=UTC),
            licence="l",
            attribution="a",
        )


def test_programme_period_defaults_to_unknown():
    assert _section().programme_period is ProgrammePeriod.UNKNOWN


def test_sections_are_immutable():
    s = _section()
    with pytest.raises(ValidationError):
        s.text = "rewritten"
