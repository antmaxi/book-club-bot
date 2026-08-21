#!/usr/bin/env bash
# Per-boot guard for club-voting-bot's dev environment.
# The project venv lives at the repo root (scripts/precommit_checks.sh expects
# $ROOT/.venv) and is gitignored, so a boot-time checkout can wipe it. Recreate it
# only when it is missing; this is a no-op on normal boots where install already ran.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ ! -x "$ROOT/.venv/bin/pytest" ]; then
    echo "club-voting-bot: .venv missing, running install..."
    bash "$ROOT/.cursor/install.sh"
fi
