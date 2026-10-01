"""The access filter must be in the SQL, and must default closed.

These are unit tests over the WHERE-clause builder, so they run with no
database. The end-to-end check (a restricted row actually withheld from a
real query, across all three retrieval modes) is recorded in
docs/containerisation-plan.md under phase 9.

Worth stating why this is tested at all: a model instruction is not an access
control, so the only thing standing between a restricted section and a user
who should not see it is this clause.
"""

from __future__ import annotations

from gcr.db import PUBLIC_GROUP, _filters


def test_access_group_is_always_filtered() -> None:
    """Every query carries the clause -- there is no code path without it."""
    where, params = _filters([PUBLIC_GROUP], None, None)
    assert "access_group = ANY(%s)" in where
    assert params[0] == [PUBLIC_GROUP]


def test_no_groups_means_public_only_not_everything() -> None:
    """A caller that does not say who it is gets the public tier.

    The dangerous failure would be treating "no groups" as "no filter".
    """
    where, params = _filters([], None, None)
    assert "access_group = ANY(%s)" in where
    assert params[0] == [PUBLIC_GROUP]


def test_restricted_group_is_additive_not_replacing() -> None:
    where, params = _filters([PUBLIC_GROUP, "restricted"], None, None)
    assert params[0] == [PUBLIC_GROUP, "restricted"]
    assert "access_group = ANY(%s)" in where


def test_country_filter_is_parameterised_and_upper_cased() -> None:
    """Upper-cased to match the iso_country domain; parameterised so a country
    string can never become SQL."""
    where, params = _filters([PUBLIC_GROUP], "ie", None)
    assert "country = %s" in where
    assert "IE" in params
    assert "'IE'" not in where


def test_country_filter_keeps_rows_that_are_not_country_bound() -> None:
    """A section with no country is EU-wide guidance and applies everywhere, so
    a country filter must not hide it."""
    where, _ = _filters([PUBLIC_GROUP], "IE", None)
    assert "country IS NULL" in where


def test_programme_period_filter() -> None:
    where, params = _filters([PUBLIC_GROUP], None, "2021-2027")
    assert "programme_period = %s" in where
    assert "2021-2027" in params


def test_filters_compose() -> None:
    where, params = _filters([PUBLIC_GROUP, "restricted"], "DE", "2028-2034")
    assert where.count(" AND ") == 2
    assert params == [[PUBLIC_GROUP, "restricted"], "DE", "2028-2034"]
