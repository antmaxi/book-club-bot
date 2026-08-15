#!/usr/bin/env bash
# Idempotent Cloud Agent install for book-club-bot.
# Creates a project virtualenv and installs runtime + dev dependencies.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# The venv module needs ensurepip, which the base image may not ship. Install the
# matching python3-venv package on demand so this works on a bare default image.
if ! python3 -c "import ensurepip" >/dev/null 2>&1; then
    pyver="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
    sudo apt-get update -qq
    sudo apt-get install -y -qq "python${pyver}-venv"
fi

python3 -m venv .venv
.venv/bin/pip install --upgrade pip
# requirements-dev.txt pulls in requirements.txt plus ruff/black/mypy/pytest/pre-commit.
.venv/bin/pip install -r requirements-dev.txt

echo "book-club-bot dev environment ready. Activate with: source .venv/bin/activate"
