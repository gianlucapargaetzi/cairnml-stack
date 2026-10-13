#!/bin/sh
# Builds the client wheels that job environments install, into the agent home's wheels dir.
set -eu
cd "$(dirname "$0")/../.."
OUT="${1:?usage: build-wheels.sh OUT_DIR}"
mkdir -p "$OUT"
rm -f "$OUT"/mlops_client-*.whl "$OUT"/mlops_common-*.whl
uv build --wheel --package mlops-common -o "$OUT"
uv build --wheel --package mlops-client -o "$OUT"
ls "$OUT"
