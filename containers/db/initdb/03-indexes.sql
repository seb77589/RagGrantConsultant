-- Indexes created at initialisation.
--
-- The HNSW vector index is deliberately NOT here. Building HNSW on an empty
-- table and then inserting 50,000+ rows is far slower than bulk-loading and
-- building afterwards, and phase 6.2 of docs/containerisation-plan.md needs to
-- *time* that build to answer whether the 500,000-section cap can be relaxed.
-- So it is created by containers/db/hnsw.sql after the load, where the timing
-- means something.
--
-- Everything below is cheap on an empty table and wanted from the first insert.

-- Keyword half of hybrid retrieval.
CREATE INDEX sections_tsv_gin            ON sections USING gin (tsv);
CREATE INDEX sections_translated_tsv_gin ON sections_translated USING gin (tsv);

-- The structured eligibility filter runs *before* the vector search, so these
-- carry the selectivity. Country first because almost every query is
-- country-bound and 100% of CORDIS sections have one.
CREATE INDEX sections_country           ON sections (country) WHERE country IS NOT NULL;
CREATE INDEX sections_nuts              ON sections (nuts_code) WHERE nuts_code IS NOT NULL;
CREATE INDEX sections_programme_period  ON sections (programme, programme_period);

-- Access filtering is applied to every retrieval query, so it is worth an
-- index even at low cardinality: it keeps the planner from choosing a seq scan
-- once the restricted tier is non-trivial.
CREATE INDEX sections_access_group            ON sections (access_group);
CREATE INDEX sections_translated_access_group ON sections_translated (access_group);

-- Citation and staleness lookups: "what do we hold for this CELEX number",
-- "what is older than N months".
CREATE INDEX sections_source           ON sections (source_system, source_id);
CREATE INDEX sections_source_date      ON sections (source_date DESC NULLS LAST);

-- Identifiers are not words, so full-text search handles them badly. Trigram
-- matching covers "topic HORIZON-CL4-2024" and partial organisation names.
CREATE INDEX sections_source_id_trgm   ON sections USING gin (source_id gin_trgm_ops);

-- Which rows still need embedding. Partial, so it stays small and is empty
-- once a pass completes -- making "is the corpus fully embedded?" a cheap
-- question rather than a full scan.
CREATE INDEX sections_embedding_missing ON sections (section_id) WHERE embedding IS NULL;

-- Ties rows back to the ingestion run and manifest entry that produced them.
CREATE INDEX sections_chunking_version ON sections (chunking_version);
