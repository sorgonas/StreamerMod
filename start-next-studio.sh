#!/bin/sh
set -eu
cd "$(dirname "$0")"
# Explicit test modes remain available; ordinary starts run live.
for argument in "$@"; do
    case "$argument" in
        --live|--preview|--obs-test)
            exec .venv-linux/bin/python -m sorgobot.next_desktop "$@"
            ;;
    esac
done
exec .venv-linux/bin/python -m sorgobot.next_desktop --live "$@"
