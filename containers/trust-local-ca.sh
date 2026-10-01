#!/usr/bin/env bash
#
# Extract Caddy's local CA certificate and install it into the system trust
# store.
#
# Why this is a script rather than a line in the README: Caddy normally
# installs its own root CA automatically, but it cannot do that from inside a
# container -- it has no access to the host trust store. Without this step the
# first visit to https://grants.localhost shows a certificate warning, which
# looks exactly like a broken deployment and is not.
#
# Firefox and Chrome on Linux keep their own certificate stores and do NOT read
# the system one for this purpose, so the browser import at the end is a
# separate, manual step. There is no way around it.
#
#   ./containers/trust-local-ca.sh            # extract and show instructions
#   ./containers/trust-local-ca.sh --install  # also run update-ca-certificates
#
set -euo pipefail

cd "$(dirname "$0")/.."

# shellcheck disable=SC1091
set -a; [[ -f .env ]] && . ./.env; set +a

PROJECT="${COMPOSE_PROJECT_NAME:-gcr}"
CA_IN_CONTAINER="/data/caddy/pki/authorities/local/root.crt"
OUT="caddy-local-ca.crt"

if ! docker ps --format '{{.Names}}' | grep -q "^${PROJECT}-caddy-1$"; then
    echo "caddy is not running. Start it first:" >&2
    echo "  docker compose --profile edge up -d" >&2
    exit 1
fi

docker cp "${PROJECT}-caddy-1:${CA_IN_CONTAINER}" "$OUT"
echo "extracted  $OUT"
openssl x509 -in "$OUT" -noout -subject -dates | sed 's/^/           /'

if [[ "${1:-}" == "--install" ]]; then
    echo
    echo "installing into the system trust store (needs sudo)"
    sudo cp "$OUT" /usr/local/share/ca-certificates/caddy-gcr-local-ca.crt
    sudo update-ca-certificates
    echo "done. curl and anything else using the system store now trust it."
else
    echo
    echo "To install into the system trust store:"
    echo "  sudo cp $OUT /usr/local/share/ca-certificates/caddy-gcr-local-ca.crt"
    echo "  sudo update-ca-certificates"
fi

cat <<'EOF'

Browsers do not use the system store for this. Import it separately:

  Firefox  Settings -> Privacy & Security -> Certificates -> View Certificates
           -> Authorities -> Import -> select the .crt
           -> tick "Trust this CA to identify websites"

  Chrome   Settings -> Privacy and security -> Security -> Manage certificates
           -> Authorities -> Import -> select the .crt

The CA lives on the gcr_caddy_data volume. It survives `docker compose down`
and a container recreate, but NOT `down -v` -- removing that volume generates a
new CA, and everything above has to be redone.
EOF
