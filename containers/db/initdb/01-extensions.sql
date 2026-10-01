-- Extensions.
--
-- vector   : HNSW index and the vector type, for the dense half of hybrid retrieval.
-- pg_trgm  : trigram similarity, for fuzzy matching on identifiers and
--            organisation names where full-text search is the wrong tool
--            (a CELEX number or a topic identifier is not a word).
-- unaccent : folds diacritics. The corpus is English-origin, but organisation
--            and place names in it are not -- "Göteborg", "Lodz", "Côte".

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;

-- Recorded so the migration-equivalence proof can assert that the restore
-- target carries the same extension versions as the source. A difference in
-- pgvector version between source and target would be a legitimate
-- explanation for a difference in retrieval results, and we want to be able
-- to rule it in or out rather than guess.
DO $$
BEGIN
    RAISE NOTICE 'vector %, pg_trgm %, unaccent %',
        (SELECT extversion FROM pg_extension WHERE extname = 'vector'),
        (SELECT extversion FROM pg_extension WHERE extname = 'pg_trgm'),
        (SELECT extversion FROM pg_extension WHERE extname = 'unaccent');
END $$;
