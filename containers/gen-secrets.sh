#!/usr/bin/env bash
#
# Generate .env and secrets/ for the containerised stack.
#
# Idempotent by design: anything that already exists is left alone and
# reported as "keep". Rotating a secret that services are already using
# breaks sessions and, for the storage encryption key, makes existing
# Authelia rows unreadable -- so rotation has to be a deliberate act
# (delete the file yourself), never a side effect of re-running this.
#
#   ./containers/gen-secrets.sh
#
set -euo pipefail

cd "$(dirname "$0")/.."

SECRETS_DIR="secrets"
ENV_FILE=".env"
ENV_TEMPLATE=".env.example"

mkdir -p "$SECRETS_DIR"
chmod 700 "$SECRETS_DIR"

# Emit exactly $1 characters from [A-Za-z0-9]. Over-generate first: base64 of
# N bytes is ~1.37N characters, and stripping '=+/' removes an unpredictable
# share of them, so asking openssl for exactly the target length yields a
# short string. Authelia rejects a storage encryption key under 64 characters,
# and the resulting error does not say so clearly -- hence the loop.
rand() {
    local want="${1:-43}" out=""
    while (( ${#out} < want )); do
        out+=$(openssl rand -base64 "$((want * 2))" | tr -d '\n=+/')
    done
    printf '%s' "${out:0:want}"
}

# Authelia and LLDAP read these from files via their *_FILE environment
# variables, which is the method Authelia documents as preferred over
# inlining values into the config.
write_secret() {
    local name="$1" length="${2:-43}" path="$SECRETS_DIR/$1"
    if [[ -s "$path" ]]; then
        printf '  keep      %s\n' "$name"
    else
        rand "$length" > "$path"
        chmod 600 "$path"
        printf '  generated %s (%d chars)\n' "$name" "$length"
    fi
}

echo "secrets/"
write_secret authelia_session_secret              64
write_secret authelia_storage_encryption_key      64   # Authelia requires >= 64
write_secret authelia_jwt_secret                  64   # identity_validation reset-password JWT
write_secret authelia_oidc_hmac_secret            64   # only used if OIDC is enabled later
write_secret lldap_jwt_secret                     64
write_secret lldap_key_seed                       64

# The LDAP bind password is shared: LLDAP sets it for its admin account, and
# Authelia binds with it. One value, two consumers, so it is generated once
# and both read the same file. No '$' in it -- LLDAP requires escaping those.
write_secret ldap_admin_password                  32

# Database passwords live in .env rather than secrets/, because the Postgres
# image takes them as plain environment variables at initdb time and compose
# needs them to build DATABASE_URL.
echo
echo "$ENV_FILE"
if [[ -f "$ENV_FILE" ]]; then
    echo "  keep      $ENV_FILE already exists; not touching it"
    echo "            (delete it and re-run to regenerate)"
else
    cp "$ENV_TEMPLATE" "$ENV_FILE"
    # Fill the two required blanks and match the mounts to the invoking user.
    sed -i \
        -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(rand 43)|" \
        -e "s|^AUTHELIA_DB_PASSWORD=.*|AUTHELIA_DB_PASSWORD=$(rand 43)|" \
        -e "s|^HOST_UID=.*|HOST_UID=$(id -u)|" \
        -e "s|^HOST_GID=.*|HOST_GID=$(id -g)|" \
        "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    echo "  generated $ENV_FILE with fresh database passwords"
    echo "            HOST_UID=$(id -u) HOST_GID=$(id -g)"
fi

echo
echo "Both .env and secrets/ are gitignored. Commit only the *.example files."
