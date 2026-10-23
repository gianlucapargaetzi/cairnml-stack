#!/usr/bin/env bash
# Removes the mlops setup from this machine:
#   1. the local sign-in keys and the CairnML config that point at our server (revokes this machine's access),
#   2. the containers, volumes and network of the stack (deploy/compose.yaml),
#   3. the data of the stack: users, databases, logs, and the Keycloak data,
#   4. the images built for the stack,
#   5. (optional) everything else in Docker.
#
# Kept unless you ask for it:
#   --include-nas       the artifact and dataset store (deploy/data/nas)
#   --include-secrets   deploy/secrets and deploy/.env (signing keys, GitHub App key, admin password)
#   --prune-docker      images, networks and volumes of other projects on this machine
#
# Run with --dry-run first. Without --yes you must type the confirmation phrase.
set -euo pipefail
cd "$(dirname "$0")/.."
DEPLOY_DIR="$PWD"

DRY_RUN=0
ASSUME_YES=0
INCLUDE_NAS=0
INCLUDE_SECRETS=0
PRUNE_DOCKER=0

usage() {
  cat <<'EOF'
Usage: deploy/scripts/teardown.sh [options]

Options:
  --dry-run           print what would be removed, change nothing
  --yes               skip the confirmation phrase
  --include-nas       also remove the artifact and dataset store
  --include-secrets   also remove deploy/secrets and deploy/.env
  --prune-docker      also run docker system prune -a --volumes (every unused image, network and volume)
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --yes) ASSUME_YES=1 ;;
    --include-nas) INCLUDE_NAS=1 ;;
    --include-secrets) INCLUDE_SECRETS=1 ;;
    --prune-docker) PRUNE_DOCKER=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage >&2; exit 1 ;;
  esac
  shift
done

say() { printf '%s\n' "$*"; }

# run CMD... : executes the command, or only prints it with --dry-run
run() {
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '  would run: %s\n' "$*"
  else
    "$@"
  fi
}

# wipe_dir DIR : removes a folder through a throwaway container, because the files inside are
# owned by users that do not exist on this machine (the stack's containers write as them)
wipe_dir() {
  local parent base
  parent="$(dirname "$1")"
  base="$(basename "$1")"
  if [ ! -e "$1" ]; then
    say "  skip: $1 does not exist"
    return
  fi
  if [ "$DRY_RUN" -eq 1 ]; then
    say "  would remove: $1"
  else
    docker run --rm -v "$parent:/wipe" alpine:3.20 rm -rf "/wipe/$base"
    say "  removed: $1"
  fi
}

# ---------------------------------------------------------------- plan
say "mlops teardown"
say "deploy folder: $DEPLOY_DIR"
say ""
say "This removes:"
say "  - the sign-in keys and the CairnML config on this machine (~/.cairnml, ~/cairnml.conf if it names our server)"
say "  - the containers, volumes and network of the stack (deploy/compose.yaml)"
say "  - the data of the stack: deploy/data/cairnml (users, MongoDB, Redis, Elasticsearch, logs), deploy/data/idp (Keycloak), deploy/data/postgres"
say "  - the images cairnml-server-fork:local and the Keycloak image"
[ "$INCLUDE_NAS" -eq 1 ] && say "  - deploy/data/nas: artifacts and datasets (--include-nas)"
[ "$INCLUDE_SECRETS" -eq 1 ] && say "  - deploy/secrets and deploy/.env (--include-secrets)"
[ "$PRUNE_DOCKER" -eq 1 ] && say "  - every unused Docker image, network and volume on this machine, including other projects (--prune-docker)"
say ""
say "Kept: the source code, the submodules, docs, the /etc/hosts line, and the other Docker projects (unless --prune-docker)."
say ""

if [ "$DRY_RUN" -eq 0 ] && [ "$ASSUME_YES" -eq 0 ]; then
  say "Type 'delete mlops' to continue:"
  read -r answer
  if [ "$answer" != "delete mlops" ]; then
    say "not confirmed; nothing removed"
    exit 1
  fi
fi

command -v docker >/dev/null || { echo "docker is required" >&2; exit 1; }

# ---------------------------------------------------------------- 1. this machine's access
say "1. Revoking access on this machine"
if [ -f "$HOME/.cairnml/device.key" ]; then
  run rm -f "$HOME/.cairnml/device.key"
  say "  the server keeps this device's record until step 3 removes its data"
fi
if [ -f "$HOME/.cairnml/.session.json" ]; then
  run rm -f "$HOME/.cairnml/.session.json"
fi
if [ -f "$HOME/cairnml.conf" ] && grep -q "mlops-cairnml" "$HOME/cairnml.conf"; then
  run rm -f "$HOME/cairnml.conf"
  say "  ~/cairnml.conf names the mlops-cairnml server"
fi

# ---------------------------------------------------------------- 2. containers and networks
# deploy/.env is read by compose from this folder, because compose.yaml is here.
say "2. Stopping and removing the containers"
run docker compose -f compose.yaml down -v --remove-orphans
for image in cairnml-server-fork:local; do
  if [ "$DRY_RUN" -eq 1 ] || docker image inspect "$image" >/dev/null 2>&1; then
    run docker image rm -f "$image"
  fi
done

# ---------------------------------------------------------------- 3. data
say "3. Removing the data (users, databases, logs)"
wipe_dir "$DEPLOY_DIR/data/cairnml"
wipe_dir "$DEPLOY_DIR/data/idp"
wipe_dir "$DEPLOY_DIR/data/postgres"
if [ "$INCLUDE_NAS" -eq 1 ]; then
  wipe_dir "$DEPLOY_DIR/data/nas"
else
  say "  kept: deploy/data/nas (artifacts and datasets; use --include-nas to remove)"
fi

# ---------------------------------------------------------------- 4. secrets
if [ "$INCLUDE_SECRETS" -eq 1 ]; then
  say "4. Removing the secrets"
  run rm -rf "$DEPLOY_DIR/secrets"
  run rm -f "$DEPLOY_DIR/.env"
else
  say "4. Secrets kept (deploy/secrets, deploy/.env; use --include-secrets to remove)"
fi

# ---------------------------------------------------------------- 5. the rest of Docker
if [ "$PRUNE_DOCKER" -eq 1 ]; then
  say "5. Pruning Docker: every unused image, network and volume"
  run docker system prune -a --volumes -f
else
  say "5. Other Docker projects kept (use --prune-docker to prune everything)"
fi

say ""
if [ "$DRY_RUN" -eq 1 ]; then
  say "Dry run: nothing was changed."
else
  say "Done. Run deploy/scripts/bootstrap.sh to set the stack up again; it creates the data folders and the secrets."
fi
