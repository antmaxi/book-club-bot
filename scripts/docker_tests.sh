#!/bin/bash
# Run the test suite in Docker (same image as production).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export BOT_UID="$(id -u)"
export BOT_GID="$(id -g)"
docker compose run --rm \
  -e PYTHONPATH=/app \
  -w /tmp \
  -v "$(pwd)/bookclub:/app/bookclub:ro" \
  -v "$(pwd)/bookclub_bot.py:/app/bookclub_bot.py:ro" \
  -v "$(pwd)/scripts:/app/scripts:ro" \
  -v "$(pwd)/tests:/app/tests:ro" \
  bot python -m pytest -p no:cacheprovider /app/tests/
