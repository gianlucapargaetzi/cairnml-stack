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
  for name in KC_ADMIN_PASSWORD MINIO_ROOT_PASSWORD MLOPS_S3_SECRET_KEY POSTGRES_PASSWORD; do
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

docker compose -f compose.yaml up -d --build mlops-idp mlops-nas mlops-nas-init mlops-postgres mlops-server
echo "waiting for the server..."
for _ in $(seq 1 60); do
  curl -fsS "${MLOPS_SERVER_URL}/api/v1/healthz" >/dev/null 2>&1 && { echo "server is up"; break; }
  sleep 2
done
echo "next: enroll an admin (docs/runbook.md), create a project, create an agent token, then:"
echo "  docker compose -f compose.yaml up -d mlops-agent   (from deploy/)"
