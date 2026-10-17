#!/usr/bin/env bash
# Removes the mlops-clearml setup from this machine:
#   1. the local sign-in keys and the ClearML config that point at our server (revokes this machine's access),
#   2. the containers and networks of the sign-in service and the ClearML server,
#   3. the data of the stack: users, databases, logs, and the Keycloak data,
#   4. the images we built for the stack,
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
DEV_DATA=""

usage() {
  sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'
  cat <<'EOF'

Options:
  --dry-run           print what would be removed, change nothing
  --yes               skip the confirmation phrase
  --include-nas       also remove the artifact and dataset store
  --include-secrets   also remove deploy/secrets and deploy/.env
  --prune-docker      also run docker system prune -a --volumes (every unused image, network and volume)
  --dev-data DIR      also remove the data of the development stack, e.g. ~/Documents/mlops-clearml/data
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --yes) ASSUME_YES=1 ;;
    --include-nas) INCLUDE_NAS=1 ;;
    --include-secrets) INCLUDE_SECRETS=1 ;;
    --prune-docker) PRUNE_DOCKER=1 ;;
    --dev-data) shift; DEV_DATA="${1:?--dev-data needs a directory}" ;;
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
say "mlops-clearml teardown"
say "deploy folder: $DEPLOY_DIR"
say ""
say "This removes:"
say "  - the sign-in keys and the ClearML config on this machine (~/.clearml, ~/clearml.conf if it names our server)"
say "  - the containers, volumes and network of the sign-in service and of the ClearML server (project mlops-clearml)"
say "  - the data of the stack: deploy/data/clearml (users, MongoDB, Redis, Elasticsearch, logs, file server), deploy/data/idp (Keycloak), deploy/data/postgres"
say "  - the images clearml-server-fork:local and clearml-server-idp:baseline, and the images of the sign-in service"
[ "$INCLUDE_NAS" -eq 1 ] && say "  - deploy/data/nas: artifacts and datasets (--include-nas)"
[ "$INCLUDE_SECRETS" -eq 1 ] && say "  - deploy/secrets and deploy/.env (--include-secrets)"
[ -n "$DEV_DATA" ] && say "  - the development data in $DEV_DATA (--dev-data)"
[ "$PRUNE_DOCKER" -eq 1 ] && say "  - every unused Docker image, network and volume on this machine, including other projects (--prune-docker)"
say ""
say "Kept: the source code, docs, the /etc/hosts line, and the other Docker projects (unless --prune-docker)."
say ""

if [ "$DRY_RUN" -eq 0 ] && [ "$ASSUME_YES" -eq 0 ]; then
  say "Type 'delete mlops-clearml' to continue:"
  read -r answer
  if [ "$answer" != "delete mlops-clearml" ]; then
    say "not confirmed; nothing removed"
    exit 1
  fi
fi

command -v docker >/dev/null || { echo "docker is required" >&2; exit 1; }

# ---------------------------------------------------------------- 1. this machine's access
say "1. Revoking access on this machine"
if [ -f "$HOME/.clearml/device.key" ]; then
  run rm -f "$HOME/.clearml/device.key"
  say "  the server keeps this device's record until step 3 removes its data"
fi
if [ -f "$HOME/.clearml/.session.json" ]; then
  run rm -f "$HOME/.clearml/.session.json"
fi
if [ -f "$HOME/clearml.conf" ] && grep -q "mlops-clearml" "$HOME/clearml.conf"; then
  run rm -f "$HOME/clearml.conf"
  say "  ~/clearml.conf names the mlops-clearml server"
fi

# ---------------------------------------------------------------- 2. containers and networks
say "2. Stopping and removing the containers"
# Compose looks for .env next to the first compose file (deploy/idp/), not in deploy/, so the
# variables of deploy/.env are passed explicitly
ENV_FILE_ARGS=()
if [ -f "$DEPLOY_DIR/.env" ]; then
  ENV_FILE_ARGS=(--env-file "$DEPLOY_DIR/.env")
fi
run docker compose ${ENV_FILE_ARGS[@]+"${ENV_FILE_ARGS[@]}"} -p mlops-clearml -f clearml/compose.yaml down -v --remove-orphans
run docker compose ${ENV_FILE_ARGS[@]+"${ENV_FILE_ARGS[@]}"} -f idp/compose.yaml down -v --remove-orphans
if [ -n "$DEV_DATA" ]; then
  # the development stack uses the same project name; this stops its containers too
  run docker compose ${ENV_FILE_ARGS[@]+"${ENV_FILE_ARGS[@]}"} -p mlops-clearml down -v --remove-orphans
fi
run docker network rm mlops || true
for image in clearml-server-fork:local clearml-server-idp:baseline; do
  if [ "$DRY_RUN" -eq 1 ] || docker image inspect "$image" >/dev/null 2>&1; then
    run docker image rm -f "$image"
  fi
done

# ---------------------------------------------------------------- 3. data
say "3. Removing the data (users, databases, logs)"
wipe_dir "$DEPLOY_DIR/data/clearml"
wipe_dir "$DEPLOY_DIR/data/idp"
wipe_dir "$DEPLOY_DIR/data/postgres"
if [ "$INCLUDE_NAS" -eq 1 ]; then
  wipe_dir "$DEPLOY_DIR/data/nas"
else
  say "  kept: deploy/data/nas (artifacts and datasets; use --include-nas to remove)"
fi
if [ -n "$DEV_DATA" ]; then
  wipe_dir "$DEV_DATA"
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
