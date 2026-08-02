#!/bin/bash
# Run the test suite in Docker (same image as production).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
docker compose run --rm \
  -v "$(pwd)/bookclub_bot.py:/app/bookclub_bot.py:ro" \
  -v "$(pwd)/scripts:/app/scripts:ro" \
  -v "$(pwd)/tests:/app/tests:ro" \
  bot python -m pytest tests/
