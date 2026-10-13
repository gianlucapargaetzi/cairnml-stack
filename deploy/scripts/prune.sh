#!/usr/bin/env bash
# Stops the stack and deletes all its data, so that bootstrap.sh starts from zero.
# Deletes: Keycloak users and realm state, RustFS buckets, the Postgres database.
# Keeps: deploy/.env, deploy/secrets/, the images and the wheels.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ "${1:-}" != "--yes" ]; then
  echo "This deletes all MLOps data under deploy/data/ and restarts from zero." >&2
  echo "Run: scripts/prune.sh --yes" >&2
  exit 1
fi

docker compose -f compose.yaml down --remove-orphans

# Empty the host folders as root, because the containers wrote them as their own uids.
if [ -d data ]; then
  docker run --rm -v "$PWD/data:/data" alpine:3.20 sh -c 'rm -rf /data/idp /data/nas /data/postgres'
  rmdir data 2>/dev/null || true
fi

# Named volumes from before the host-folder layout. Missing volumes are fine.
for volume in mlops_idp-data mlops_nas-data mlops_pgdata; do
  docker volume rm "$volume" >/dev/null 2>&1 && echo "removed volume $volume" || true
done

echo "data removed. Start from zero with: scripts/bootstrap.sh"
