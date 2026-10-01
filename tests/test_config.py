"""Config tests.

`DATABASE_URL` is the only environment variable in the codebase, so the two
things worth pinning are that it is read from the environment at all and that
the default works without one.
"""

from __future__ import annotations

import importlib

from gcr import config


def test_database_url_defaults_to_published_loopback_port() -> None:
    """With no environment set, a host-side run reaches compose's published port."""
    assert config.DATABASE_URL.startswith("postgresql://")
    assert "127.0.0.1:5432" in config.DATABASE_URL


def test_database_url_comes_from_the_environment(monkeypatch) -> None:
    """Compose sets the in-network form; the module must honour it."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://gcr:pw@db:5432/gcr")
    reloaded = importlib.reload(config)
    try:
        assert reloaded.DATABASE_URL == "postgresql://gcr:pw@db:5432/gcr"
    finally:
        # Other tests import this module; leave it as they expect to find it.
        monkeypatch.delenv("DATABASE_URL")
        importlib.reload(config)


def test_the_two_tiers_are_distinct_tables() -> None:
    """The translated tier is access-restricted and labelled, so it must never
    resolve to the same table as the core corpus."""
    assert config.SECTIONS_TABLE != config.SECTIONS_TRANSLATED_TABLE


def test_embedding_dimension_matches_the_schema() -> None:
    """02-schema.sql declares vector(1024). If EMBED_DIM ever changes, that is a
    new column or a new table, not an ALTER -- so this must be caught here."""
    assert config.EMBED_DIM == 1024
