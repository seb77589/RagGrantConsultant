-- Core schema.
--
-- Column names mirror src/gcr/models.py field-for-field, so a Section round
-- trips without a translation layer. Where this schema is stricter than the
-- Pydantic model, that is deliberate and noted.
--
-- The rules in CLAUDE.md that this file enforces in the database rather than
-- trusting code to honour:
--
--   * Source identity and dates are sacred. source_system, source_id,
--     source_url, fetch_date, licence and attribution are NOT NULL. source_date
--     is nullable because some upstreams genuinely publish none -- but it is a
--     column that must be explicitly set, never inferred.
--   * Country and NUTS region are first-class columns, not derived at query
--     time.
--   * programme_period exists from day one so 2028-2034 can coexist with
--     2021-2027 without a schema redesign.
--   * Machine-translated text cannot enter the core table at all: the CHECK
--     on origin rejects it. The translated tier is a separate table with its
--     own index and a restricted default access group.

-- Vocabularies as CHECK constraints over text rather than ENUM types. Both
-- survive dump/restore, but text plus CHECK is cheaper to extend when the
-- 2035-2041 programme period arrives, and keeps the migration-equivalence
-- comparison free of type-OID differences between source and target.
CREATE DOMAIN programme_period AS text
    NOT NULL DEFAULT 'unknown'
    CONSTRAINT programme_period_known
        CHECK (VALUE IN ('2014-2020', '2021-2027', '2028-2034', 'unknown'));

CREATE DOMAIN iso_country AS text
    CONSTRAINT iso_country_alpha2
        CHECK (VALUE ~ '^[A-Z]{2}$');

COMMENT ON DOMAIN programme_period IS
    'Framework programme period. Extend the CHECK, do not add a column.';
COMMENT ON DOMAIN iso_country IS
    'ISO 3166-1 alpha-2, upper case. Mirrors the validator on Section.country.';


-- ---------------------------------------------------------------------------
-- Core corpus: English-origin text only
-- ---------------------------------------------------------------------------

CREATE TABLE sections (
    section_id        text        PRIMARY KEY,

    -- Identity and dates. These drive citations, "as of" dates, staleness
    -- warnings and the migration comparison.
    source_system     text        NOT NULL CHECK (length(source_system) > 0),
    source_id         text        NOT NULL CHECK (length(source_id) > 0),
    source_url        text        NOT NULL CHECK (length(source_url) > 0),
    source_date       date,
    fetch_date        timestamptz NOT NULL,
    licence           text        NOT NULL CHECK (length(licence) > 0),
    attribution       text        NOT NULL CHECK (length(attribution) > 0),

    text              text        NOT NULL CHECK (length(btrim(text)) > 0),

    -- 'machine_translated' is absent on purpose: eTranslation output breaks the
    -- English-origin rule and belongs in sections_translated, which is indexed
    -- separately, labelled in answers and access-restricted.
    origin            text        NOT NULL
                      CHECK (origin IN ('english_origin', 'generated_from_structured')),

    -- Retrieval-time filters, stored not derived.
    country           iso_country,
    nuts_code         text,
    programme         text,
    programme_period  programme_period,

    part              text,
    ordinal           integer     NOT NULL CHECK (ordinal >= 0),
    token_count       integer     NOT NULL CHECK (token_count >= 1),

    -- Maps to an Authelia/LLDAP group. Enforced in the query path, never in a
    -- prompt: a model instruction is not an access control.
    access_group      text        NOT NULL DEFAULT 'public',

    -- Which chunking produced this row. A change to TARGET_TOKENS/MAX_TOKENS/
    -- OVERLAP_TOKENS requires a re-embed, and this is how a half-migrated
    -- corpus is detectable rather than silently mixed.
    chunking_version  text        NOT NULL,

    -- bge-m3 dense vector. Dimension is fixed at 1024 by the model; a change
    -- of embedding model is a new column or a new table, not an ALTER.
    embedding         vector(1024),

    -- The keyword half of hybrid retrieval. Generated, so it can never drift
    -- out of step with the text the way a trigger-maintained column can.
    -- `part` carries the weight of a heading, the body the weight of a body.
    tsv               tsvector GENERATED ALWAYS AS (
                          setweight(to_tsvector('english'::regconfig, coalesce(part, '')), 'B') ||
                          setweight(to_tsvector('english'::regconfig, text), 'C')
                      ) STORED,

    inserted_at       timestamptz NOT NULL DEFAULT now(),

    -- section_id is defined as <source_system>:<source_id>:<ordinal>, so the
    -- triple must be unique too. A duplicate here means an adapter emitted the
    -- same section twice, which would double its weight in retrieval.
    CONSTRAINT sections_source_ordinal_unique
        UNIQUE (source_system, source_id, ordinal)
);

COMMENT ON TABLE sections IS
    'Core corpus. English-origin text only; machine translation is rejected by CHECK.';
COMMENT ON COLUMN sections.source_date IS
    'Upstream last-change date. NULL only where upstream truly publishes none -- never guessed.';
COMMENT ON COLUMN sections.access_group IS
    'Authelia/LLDAP group required to retrieve this row. Filtered in SQL, not in the prompt.';
COMMENT ON COLUMN sections.embedding IS
    'bge-m3 dense, 1024 dimensions, CLS-pooled. NULL until the embedding pass has run.';


-- ---------------------------------------------------------------------------
-- Translated tier: separate table, separate index, restricted by default
-- ---------------------------------------------------------------------------
--
-- Kohesio's English is eTranslation output. Its structured fields (numbers,
-- codes, regions) belong in the core table as generated_from_structured
-- sentences; its translated prose, if ever ingested, lives here. Answers that
-- draw on this table must say so.
--
-- LIKE keeps the column list in step with sections automatically -- including
-- the generated tsv column -- so the two tiers cannot drift apart. The
-- constraints differ, so they are added explicitly below rather than copied.

CREATE TABLE sections_translated (
    LIKE sections
        INCLUDING DEFAULTS
        INCLUDING GENERATED
        INCLUDING COMMENTS
);

ALTER TABLE sections_translated
    ADD PRIMARY KEY (section_id),
    ADD CONSTRAINT sections_translated_source_ordinal_unique
        UNIQUE (source_system, source_id, ordinal),
    -- The mirror image of the core table's rule: this tier is *only* for
    -- translated text, so nothing else can be hidden in here either.
    ADD CONSTRAINT sections_translated_origin
        CHECK (origin = 'machine_translated'),
    ALTER COLUMN access_group SET DEFAULT 'restricted';

COMMENT ON TABLE sections_translated IS
    'Machine-translated tier (eTranslation). Labelled in answers, access-restricted, '
    'never merged into the core corpus. Kept out of sections by CHECK on both sides.';


-- ---------------------------------------------------------------------------
-- Ingestion runs, for traceability and the migration proof
-- ---------------------------------------------------------------------------

CREATE TABLE ingestion_runs (
    run_id            bigserial   PRIMARY KEY,
    started_at        timestamptz NOT NULL DEFAULT now(),
    finished_at       timestamptz,
    source_system     text        NOT NULL,
    dataset           text        NOT NULL,
    -- sha256 of the fetched payload, matching data/reference/source_manifest.jsonl,
    -- so a row in the database can be traced back to the exact bytes it came from.
    source_sha256     text        CHECK (source_sha256 IS NULL OR length(source_sha256) = 64),
    chunking_version  text        NOT NULL,
    embed_model       text        NOT NULL,
    sections_written  integer     CHECK (sections_written IS NULL OR sections_written >= 0),
    note              text
);

COMMENT ON TABLE ingestion_runs IS
    'One row per ingestion pass. Ties database contents to a manifest entry and a '
    'chunking/embedding version, which is what makes the migration comparison auditable.';
