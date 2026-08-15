#!/usr/bin/env bash
# Idempotent Cloud Agent install for book-club-bot.
# Creates a project virtualenv and installs runtime + dev dependencies.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

python3 -m venv .venv
.venv/bin/pip install --upgrade pip
# requirements-dev.txt pulls in requirements.txt plus ruff/black/mypy/pytest/pre-commit.
.venv/bin/pip install -r requirements-dev.txt

echo "book-club-bot dev environment ready. Activate with: source .venv/bin/activate"
