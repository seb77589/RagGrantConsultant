#!/usr/bin/env bash
#
# Create Authelia's own database and role on this instance.
#
# Authelia shares the PostgreSQL instance rather than running its own: one
# fewer container, one backup target. It gets a separate database and a
# separate role -- not a schema inside the corpus database -- so that a
# compromise or a mistake on one side cannot read the other.
#
# Scripts in /docker-entrypoint-initdb.d run once, on an empty data
# directory. Changing this file does not affect an existing volume.
#
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-SQL
	CREATE ROLE "${AUTHELIA_DB_USER}" LOGIN PASSWORD '${AUTHELIA_DB_PASSWORD}';
	CREATE DATABASE "${AUTHELIA_DB_NAME}" OWNER "${AUTHELIA_DB_USER}";
	-- Authelia manages its own schema via migrations; it only needs to be
	-- able to connect and own its objects.
	REVOKE ALL ON DATABASE "${AUTHELIA_DB_NAME}" FROM PUBLIC;
	GRANT CONNECT ON DATABASE "${AUTHELIA_DB_NAME}" TO "${AUTHELIA_DB_USER}";
SQL

echo "initdb: created database ${AUTHELIA_DB_NAME} owned by ${AUTHELIA_DB_USER}"
