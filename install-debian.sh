#!/usr/bin/env bash
# Compatibility entry point; the full installer lives in install.sh.
set -euo pipefail
exec bash "$(dirname -- "$0")/install.sh" "$@"
