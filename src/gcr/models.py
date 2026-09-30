"""Core records.

`Section` is the unit that gets embedded, retrieved and cited. Every field that
CLAUDE.md marks sacred is required here rather than optional, so a source
adapter cannot produce a section that is uncitable or unattributable.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProgrammePeriod(StrEnum):
    """Programme period, present from day one so 2028-2034 can sit alongside.

    See CLAUDE.md: adding the successor framework programmes must not require a
    schema redesign.
    """

    P2014_2020 = "2014-2020"
    P2021_2027 = "2021-2027"
    P2028_2034 = "2028-2034"
    UNKNOWN = "unknown"


class Origin(StrEnum):
    """How the English text came to exist.

    The corpus rule is English-origin only. `MACHINE_TRANSLATED` exists so that
    Kohesio-style text can be represented and kept out of the core partition,
    never so that it can be quietly mixed in.
    """

    ENGLISH_ORIGIN = "english_origin"
    GENERATED_FROM_STRUCTURED = "generated_from_structured"
    MACHINE_TRANSLATED = "machine_translated"


class SourceRef(BaseModel):
    """Identity and dates for one upstream document.

    Carried onto every section derived from it. `source_id` is the upstream
    identifier in its native scheme: a CELEX number for legislation, a topic
    identifier for calls, a project number for CORDIS.
    """

    model_config = ConfigDict(frozen=True)

    source_system: str = Field(min_length=1, description="e.g. 'cordis', 'eurlex', 'sedia'")
    source_id: str = Field(min_length=1, description="upstream identifier in its native scheme")
    source_url: str = Field(min_length=1, description="canonical public URL for citation")
    source_date: date | None = Field(
        description="upstream last-change date; None only when upstream truly publishes none"
    )
    fetch_date: datetime = Field(description="when we retrieved it, for 'as of' and staleness")
    licence: str = Field(min_length=1, description="e.g. 'CC-BY-4.0', 'Decision 2011/833/EU'")
    attribution: str = Field(min_length=1, description="credit line, e.g. '© European Union'")


class Section(BaseModel):
    """One retrievable, citable chunk of text."""

    model_config = ConfigDict(frozen=True)

    section_id: str = Field(
        min_length=1, description="stable: <source_system>:<source_id>:<ordinal>"
    )
    source: SourceRef
    text: str = Field(min_length=1)
    origin: Origin

    # Retrieval-time filters. Country and NUTS are first-class per CLAUDE.md,
    # not derived at query time.
    country: str | None = Field(
        default=None, description="ISO 3166-1 alpha-2, or None if not country-bound"
    )
    nuts_code: str | None = Field(default=None, description="NUTS region code where known")
    programme: str | None = Field(default=None, description="e.g. 'HORIZON'")
    programme_period: ProgrammePeriod = ProgrammePeriod.UNKNOWN

    # Provenance within the upstream document, so a citation can point at the
    # part of the document the text came from.
    part: str | None = Field(default=None, description="e.g. 'objective', 'article 3'")
    ordinal: int = Field(ge=0, description="position among sections from the same source document")
    token_count: int = Field(ge=1)

    @field_validator("country")
    @classmethod
    def _upper_iso2(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip().upper()
        if len(v) != 2 or not v.isalpha():
            raise ValueError(f"country must be ISO 3166-1 alpha-2, got {v!r}")
        return v

    @field_validator("text")
    @classmethod
    def _no_blank_text(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("section text must not be blank")
        return v


class FetchRecord(BaseModel):
    """One line of the source manifest: proof of what was fetched, when.

    The manifest is committed; the payloads it describes are gitignored. It is
    what makes an ingestion run reproducible and the migration comparison
    auditable.
    """

    source_system: str
    url: str
    path: str = Field(description="path relative to the repo root")
    sha256: str = Field(min_length=64, max_length=64)
    bytes: int = Field(ge=0)
    fetch_date: datetime
    upstream_last_modified: str | None = None
    licence: str
    attribution: str
    note: str | None = None
