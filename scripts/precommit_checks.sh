#!/bin/bash
# Shared checks for git pre-commit and local CI. Run from repo root:
#   ./scripts/precommit_checks.sh
#
# Equivalent to: pre-commit run --all-files && bash scripts/docker_tests.sh
# (docker tests run here on every invocation; pre-push hook also runs them via
# .pre-commit-config.yaml when using `pre-commit install --install-hooks`.)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

venv_bin() {
    local name="$1"
    if [ -x "$ROOT/.venv/bin/$name" ]; then
        echo "$ROOT/.venv/bin/$name"
    elif command -v "$name" >/dev/null 2>&1; then
        echo "$name"
    else
        echo "Missing $name. Install dev dependencies:" >&2
        echo "  python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements-dev.txt" >&2
        exit 1
    fi
}

RUFF="$(venv_bin ruff)"
BLACK="$(venv_bin black)"
MYPY="$(venv_bin mypy)"
PYTEST="$(venv_bin pytest)"

TARGETS=(bookclub bookclub_bot.py scripts/check_bot_idle.py tests/)

echo "Running ruff..."
"$RUFF" check "${TARGETS[@]}"

echo "Running black..."
"$BLACK" --check "${TARGETS[@]}"

echo "Running mypy..."
"$MYPY"

echo "Running pytest..."
"$PYTEST" tests/

echo "Running docker tests..."
bash "$ROOT/scripts/docker_tests.sh"

echo "All pre-commit checks passed."
