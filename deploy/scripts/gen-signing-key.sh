#!/bin/sh
# Usage: gen-signing-key.sh PATH   (Ed25519 key the server signs access tokens with)
set -eu
openssl genpkey -algorithm ed25519 -out "$1"
chmod 600 "$1"
