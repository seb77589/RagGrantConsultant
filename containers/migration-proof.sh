#!/usr/bin/env bash
#
# Migration-equivalence proof.
#
# Dump the corpus, restore it into a second PostgreSQL on a second, empty
# volume -- the "new data centre" -- and show that retrieval is equivalent
# before and after.
#
# What is compared matters. Equal row counts would pass while an index had
# failed to restore and every ranking had silently changed, so the comparison
# is over *retrieval results*: the set of section identifiers returned, their
# order, and the scores, for a fixed question set.
#
#   ./containers/migration-proof.sh
#
set -euo pipefail

cd "$(dirname "$0")/.."

# shellcheck disable=SC1091
set -a; [[ -f .env ]] && . ./.env; set +a

PROJECT="${COMPOSE_PROJECT_NAME:-gcr}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
SNAPSHOT_DIR="data/snapshots"
DUMP="${SNAPSHOT_DIR}/${POSTGRES_DB}-${STAMP}.dump"
COMPOSE=(docker compose -f compose.yaml -f compose.proof.yaml)

mkdir -p "$SNAPSHOT_DIR"

echo "== 1. freeze and dump the source =="
# Custom format: compressed, and restorable selectively if ever needed.
docker exec -e PGPASSWORD="$POSTGRES_PASSWORD" "${PROJECT}-db-1" \
    pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --compress=6 \
    > "$DUMP"
echo "   $DUMP  $(numfmt --to=iec "$(stat -c %s "$DUMP")" 2>/dev/null || stat -c %s "$DUMP")"
echo "   sha256 $(sha256sum "$DUMP" | cut -c1-32)..."

echo
echo "== 2. bring up the target on an empty volume =="
"${COMPOSE[@]}" --profile proof up -d db-proof >/dev/null
for _ in $(seq 1 30); do
    [[ "$(docker inspect -f '{{.State.Health.Status}}' "${PROJECT}-db-proof-1" 2>/dev/null)" == "healthy" ]] && break
    sleep 2
done
echo "   ${PROJECT}-db-proof-1 healthy on volume ${PROJECT}_pgdata_proof"

echo
echo "== 3. restore =="
docker exec -i -e PGPASSWORD="$POSTGRES_PASSWORD" "${PROJECT}-db-proof-1" \
    pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --exit-on-error \
    < "$DUMP"
echo "   restored"

echo
echo "== 4. compare retrieval, source against target =="
docker compose --profile tools run --rm --no-deps \
    -e POSTGRES_USER="$POSTGRES_USER" \
    -e POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
    -e POSTGRES_DB="$POSTGRES_DB" \
    -v "$PWD/containers/compare_retrieval.py:/app/compare_retrieval.py:ro" \
    --entrypoint python pipeline /app/compare_retrieval.py

echo
echo "The proof target is still running. To destroy it and confirm the source"
echo "is untouched:"
echo "  ${COMPOSE[*]} --profile proof down"
echo "  docker volume rm ${PROJECT}_pgdata_proof"
