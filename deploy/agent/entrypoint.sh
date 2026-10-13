#!/bin/sh
set -eu
HOME_DIR="${MLOPS_AGENT_HOME:-/var/lib/mlops-agent}"
if [ ! -f "$HOME_DIR/agent.json" ]; then
  if [ -z "${MLOPS_AGENT_ENROLL_TOKEN:-}" ]; then
    echo "mlops-agent: not enrolled and MLOPS_AGENT_ENROLL_TOKEN is empty." >&2
    echo "Create a token with an admin account: POST /api/v1/admin/agent-tokens" >&2
    exit 1
  fi
  mlops-agent enroll
fi
exec mlops-agent run
