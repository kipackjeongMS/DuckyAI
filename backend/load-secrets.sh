#!/bin/sh
# load-secrets.sh — Container entrypoint wrapper.
# Reads secret files from /run/secrets/ into environment variables,
# then exec's the original command.
#
# Mapping:
#   /run/secrets/github_token       → GITHUB_TOKEN
#   /run/secrets/azure_devops_pat   → AZURE_DEVOPS_EXT_PAT

SECRETS_DIR="${DUCKYAI_SECRETS_DIR:-/run/secrets}"

if [ -d "$SECRETS_DIR" ]; then
    if [ -f "$SECRETS_DIR/github_token" ]; then
        export GITHUB_TOKEN="$(cat "$SECRETS_DIR/github_token")"
    fi
    if [ -f "$SECRETS_DIR/azure_devops_pat" ]; then
        export AZURE_DEVOPS_EXT_PAT="$(cat "$SECRETS_DIR/azure_devops_pat")"
    fi
fi

exec "$@"
