#!/usr/bin/env bash
# One-time local setup: network, hosts check, secrets, wheels, then the stacks that need no enrollment.
set -euo pipefail
cd "$(dirname "$0")/.."

command -v docker >/dev/null || { echo "docker is required" >&2; exit 1; }
docker compose version >/dev/null || { echo "docker compose v2.20+ is required" >&2; exit 1; }
command -v openssl >/dev/null || { echo "openssl is required" >&2; exit 1; }
command -v uv >/dev/null || { echo "uv is required" >&2; exit 1; }

# The role hostnames must resolve to this machine so the host sees the same URLs as the containers.
missing=()
for host in mlops-server mlops-idp mlops-nas; do
  getent hosts "$host" | grep -q '^127\.0\.0\.1\|^::1' || missing+=("$host")
done
if [ "${#missing[@]}" -gt 0 ]; then
  echo "Add this line to /etc/hosts, then re-run:" >&2
  echo "  127.0.0.1 ${missing[*]}" >&2
  exit 1
fi

docker network inspect mlops >/dev/null 2>&1 || docker network create mlops
mkdir -p secrets

[ -f secrets/signing.pem ] || scripts/gen-signing-key.sh secrets/signing.pem

if [ ! -f .env ]; then
  cp .env.example .env
  for name in KC_ADMIN_PASSWORD RUSTFS_ROOT_PASSWORD MLOPS_S3_SECRET_KEY POSTGRES_PASSWORD IDP_SYNC_SECRET; do
    sed -i "s|^${name}=.*|${name}=$(openssl rand -hex 16)|" .env
  done
  agent_home="$HOME/.local/share/mlops-agent"
  sed -i "s|^MLOPS_AGENT_HOME=.*|MLOPS_AGENT_HOME=${agent_home}|" .env
  echo "wrote deploy/.env with generated secrets"
fi

set -a; . ./.env; set +a
mkdir -p "$MLOPS_AGENT_HOME/wheels"
scripts/build-wheels.sh "$MLOPS_AGENT_HOME/wheels"
common=$(basename "$(ls "$MLOPS_AGENT_HOME"/wheels/mlops_common-*.whl | head -n1)")
client=$(basename "$(ls "$MLOPS_AGENT_HOME"/wheels/mlops_client-*.whl | head -n1)")
# The setup container sees the wheels directory at /wheels, so the pip spec uses those paths.
# Quoted so that `. ./.env` in this script keeps working on re-runs.
spec_in_container="/wheels/${client} /wheels/${common}"
sed -i "s|^MLOPS_AGENT_CLIENT_PIP_SPEC=.*|MLOPS_AGENT_CLIENT_PIP_SPEC=\"${spec_in_container}\"|" .env

if [ ! -f secrets/github-app.pem ]; then
  echo "NOTE: secrets/github-app.pem is missing. Jobs that clone code need a GitHub App;" >&2
  echo "      see docs/runbook.md. The server starts without it, but dispatch will answer 503." >&2
fi

# The stack keeps its data in host folders (deploy/data/, git-ignored). Each folder must belong to
# the uid its container runs as: Keycloak 1000, RustFS 10001, Postgres 999. Stopping the stack keeps
# them; scripts/prune.sh empties them.
mkdir -p data/idp data/nas data/postgres
docker run --rm -v "$PWD/data:/data" alpine:3.20 sh -c '
  chown 1000:1000 /data/idp && chmod 700 /data/idp &&
  chown 10001:10001 /data/nas &&
  chown 999:999 /data/postgres && chmod 700 /data/postgres'

docker compose -f compose.yaml up -d --build mlops-idp mlops-nas mlops-nas-init mlops-postgres mlops-server

# One admin login for both Keycloak's master realm and the mlops realm: KC_ADMIN and
# KC_ADMIN_PASSWORD from deploy/.env. Runs inside the idp container with kcadm, on every bootstrap,
# so the password in deploy/.env stays the one that works. Nothing is printed.
KC_USER_SETUP='
set -e
K=/opt/keycloak/bin/kcadm.sh
ok=0
for _ in $(seq 1 90); do
  if $K config credentials --server http://localhost:8180 --realm master \
       --user "$KC_MASTER_USER" --password "$KC_MASTER_PW" >/dev/null 2>&1; then ok=1; break; fi
  sleep 2
done
[ "$ok" = 1 ] || { echo "keycloak did not become ready" >&2; exit 1; }
$K set-password -r master --username "$ADMIN_USER" --new-password "$ADMIN_PW" >/dev/null
if $K get users -r mlops -q username="$ADMIN_USER" --fields username | grep -q "\"username\""; then
  $K set-password -r mlops --username "$ADMIN_USER" --new-password "$ADMIN_PW" >/dev/null
else
  $K create users -r mlops -s username="$ADMIN_USER" -s enabled=true -s emailVerified=true \
    -s email="$ADMIN_USER@example.test" -s firstName=Admin -s lastName=User >/dev/null
  $K add-roles -r mlops --uusername "$ADMIN_USER" --rolename mlops-admin
  $K set-password -r mlops --username "$ADMIN_USER" --new-password "$ADMIN_PW"
fi
'
docker compose -f compose.yaml exec -T \
  -e KC_MASTER_USER="$KC_ADMIN" -e KC_MASTER_PW="$KC_ADMIN_PASSWORD" \
  -e ADMIN_USER="$KC_ADMIN" -e ADMIN_PW="$KC_ADMIN_PASSWORD" \
  mlops-idp sh -c "$KC_USER_SETUP" >/dev/null
echo "admin login set from deploy/.env: user $KC_ADMIN, same password for Keycloak and mlops"

echo "waiting for the server..."
for _ in $(seq 1 60); do
  curl -fsS "${MLOPS_SERVER_URL}/api/v1/healthz" >/dev/null 2>&1 && { echo "server is up"; break; }
  sleep 2
done
echo "next: sign in as $KC_ADMIN (device login), create a project, create an agent token, then:"
echo "  docker compose -f compose.yaml up -d mlops-agent   (from deploy/)"
