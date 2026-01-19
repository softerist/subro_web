#!/bin/bash
# Extract version from backend/pyproject.toml
# This is the single source of truth for the application version

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
PYPROJECT="$ROOT_DIR/backend/pyproject.toml"

if [[ ! -f "$PYPROJECT" ]]; then
    echo "ERROR: $PYPROJECT not found" >&2
    exit 1
fi

grep -m1 '^version = ' "$PYPROJECT" | sed 's/version = "\(.*\)"/\1/'
