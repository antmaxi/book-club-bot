# AGENTS.md

Guidance for AI agents and new contributors working on club-voting-bot — a single-process,
long-polling Telegram bot (Python 3.11 target). Implementation lives in the `bookclub/`
package; `bookclub_bot.py` re-exports its public API. See `README.md` for the product
overview and full feature/command list.

## Dev environment

Dependencies live in a project virtualenv at the repo root (`.venv`) — `scripts/precommit_checks.sh`
expects it there. Bootstrap once, then activate for every session:

```bash
python3 -m venv .venv          # or: bash .cursor/install.sh
source .venv/bin/activate
pip install -r requirements-dev.txt   # runtime deps + ruff/black/mypy/pytest/pre-commit
```

`requirements-dev.txt` pins `ruff`/`black`/`mypy` to the exact versions enforced by
`.pre-commit-config.yaml`, so venv tools agree with the hooks.

## Canonical dev commands

Run these from the repo root with the venv activated:

```bash
ruff check bookclub bookclub_bot.py scripts/check_bot_idle.py tests/
black --check bookclub bookclub_bot.py scripts/check_bot_idle.py tests/
mypy                     # uses files/config from pyproject.toml (bookclub + bookclub_bot.py + check_bot_idle.py)
pytest tests/            # the correctness gate
```

`./scripts/precommit_checks.sh` runs the full pipeline (ruff, black, mypy, pytest, and Docker
pytest). Pre-commit hooks: `ruff`/`black`/`mypy`/`pytest` on commit, Docker pytest on pre-push
(see `README.md` → Testing for install steps). Note the commit-stage hooks lint only changed
files, so a tree-wide `ruff`/`black`/`mypy` run surfaces long-standing findings on files that
predate the current tool config — those are pre-existing, not something a small change introduced.

## Running the bot

Requires a Telegram `BOT_TOKEN` (from @BotFather) and network access; the bot fails fast with a
clear message if `BOT_TOKEN` is unset. Locally: `python bookclub_bot.py` with env vars set (see
`README.md` for the full `.env` list). Production/dev-in-container: `docker compose up`.

## Cursor Cloud specific instructions

- The dev environment is repo-file managed via `.cursor/environment.json` (`install` =
  `bash .cursor/install.sh`, `start` = `bash .cursor/start.sh`). `install.sh` installs the
  matching `python3-venv` apt package on demand, so it works on a bare default image.
- `.venv` is gitignored and lives inside the checked-out repo, so a boot-time checkout can wipe
  it. `start.sh` recreates it only when missing; if the venv ever looks broken, re-run
  `bash .cursor/install.sh` (reinstalling into the same `.venv` is safe and idempotent).
- The base image is Python 3.12 while the project targets 3.11; tests pass on 3.12 and the lint/
  type tools are configured for 3.11 semantics regardless of the interpreter.
- Running the live bot in cloud needs a `BOT_TOKEN` (and usually `ADMIN_IDS`) added as
  environment secrets; without them, validate via `pytest tests/` and offline import/wiring
  instead of `run_polling`.
