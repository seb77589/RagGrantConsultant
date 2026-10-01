#!/usr/bin/env bash
#
# Create the access groups and, optionally, a test user in LLDAP.
#
# The groups map one-to-one onto the `access_group` column on the sections
# tables, which is what the retrieval queries filter on. Adding a tier means
# adding it in three places -- here, in the schema's default, and in Authelia's
# access_control rules -- and that is deliberate: a tier that exists in only
# one of them is a leak waiting to happen.
#
# Idempotent: groups and users that already exist are reported and left alone.
#
#   ./containers/bootstrap-identity.sh                        # groups only
#   ./containers/bootstrap-identity.sh alice 's3cret'         # + a consultant
#   ./containers/bootstrap-identity.sh bob 's3cret' restricted
#
set -euo pipefail

cd "$(dirname "$0")/.."

# shellcheck disable=SC1091
set -a; [[ -f .env ]] && . ./.env; set +a

export GCR_NETWORK="${COMPOSE_PROJECT_NAME:-gcr}_backend"

# Every section is readable by one of these. `public` is the schema default and
# needs no group; `restricted` is the tier the Kohesio rule requires for
# machine-translated text, which must be labelled in answers and restricted.
exec python3 - "$@" <<'PY'
import json, subprocess, sys

NETWORK = __import__("os").environ["GCR_NETWORK"]
CURL = "curlimages/curl:8.18.0"
LLDAP = "http://lldap:17170"
GROUPS = ["consultants", "restricted"]

with open("secrets/ldap_admin_password") as fh:
    admin_password = fh.read().strip()


def curl(path, payload=None, token=None):
    cmd = ["docker", "run", "--rm", "--network", NETWORK, CURL, "-sS", "-X", "POST",
           f"{LLDAP}{path}", "-H", "Content-Type: application/json"]
    if token:
        cmd += ["-H", f"Authorization: Bearer {token}"]
    if payload is not None:
        cmd += ["-d", json.dumps(payload)]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        sys.exit(f"LLDAP returned a non-JSON response for {path}:\n{out[:400]}")


token = curl("/auth/simple/login",
             {"username": "admin", "password": admin_password})["token"]


def gql(query, **variables):
    body = {"query": query}
    if variables:
        body["variables"] = variables
    result = curl("/api/graphql", body, token=token)
    if "errors" in result:
        sys.exit(f"LLDAP GraphQL error: {result['errors']}")
    return result["data"]


existing = {g["displayName"]: g["id"] for g in gql("{groups{id displayName}}")["groups"]}

print("groups")
for name in GROUPS:
    if name in existing:
        print(f"  keep      {name}")
    else:
        created = gql(
            "mutation($n:String!){createGroup(name:$n){id displayName}}", n=name
        )["createGroup"]
        existing[name] = created["id"]
        print(f"  created   {name}")

args = sys.argv[1:]
if len(args) < 2:
    print("\nNo user requested. To add one:")
    print("  ./containers/bootstrap-identity.sh <username> <password> [group ...]")
    raise SystemExit(0)

username, password = args[0], args[1]
member_of = args[2:] or ["consultants"]

users = {u["id"] for u in gql("{users{id}}")["users"]}

print("\nuser")
if username in users:
    print(f"  keep      {username} already exists")
else:
    gql(
        "mutation($u:CreateUserInput!){createUser(user:$u){id}}",
        u={"id": username, "email": f"{username}@gcr.local", "displayName": username},
    )
    print(f"  created   {username}")

# Passwords are set with the bundled tool, not over GraphQL and not via
# /auth/simple/register -- that route serves the web page, so posting to it
# returns HTML and silently sets nothing.
subprocess.run(
    ["docker", "exec", "-e", f"LLDAP_USER_PASSWORD={password}",
     f"{__import__('os').environ.get('COMPOSE_PROJECT_NAME', 'gcr')}-lldap-1",
     "/app/lldap_set_password",
     "--base-url", "http://localhost:17170",
     "--admin-username", "admin",
     "--admin-password", admin_password,
     "--username", username],
    check=True, capture_output=True, text=True,
)
print("  password  set")

for name in member_of:
    gid = existing.get(name)
    if gid is None:
        print(f"  SKIP      no such group: {name}")
        continue
    gql(
        "mutation($u:String!,$g:Int!){addUserToGroup(userId:$u,groupId:$g){ok}}",
        u=username, g=gid,
    )
    print(f"  member of {name}")
PY
