#!/bin/bash
# Populates the REPOS bash array from the project root .env (DEPLOY_REPOS).
# Sourced by deploy_bots.sh and logs.sh.

_load_deploy_scripts_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_PROJECT_ROOT="$(cd "$_load_deploy_scripts_dir/.." && pwd)"

# Optional override: DEPLOY_ENV_FILE=/path/to/.env ./deploy_bots.sh
DEPLOY_ENV_FILE="${DEPLOY_ENV_FILE:-$DEPLOY_PROJECT_ROOT/.env}"

# Colon-separated absolute paths, e.g.:
#   DEPLOY_REPOS="/root/club-voting-bot:/root/philo-club-bot"
REPOS=()

_load_deploy_repos_from_env() {
    REPOS=()
    local env_file="$1"
    [ -f "$env_file" ] || return 1

    local line raw part
    line="$(
        grep -E '^(export[[:space:]]+)?(DEPLOY_REPOS|REPOS)=' "$env_file" 2>/dev/null | tail -n1 || true
    )"
    [ -n "$line" ] || return 1

    raw="${line#*=}"
    raw="${raw#"${raw%%[![:space:]]*}"}"
    raw="${raw%"${raw##*[![:space:]]}"}"
    if [ "${raw:0:1}" = '"' ] && [ "${raw: -1}" = '"' ]; then
        raw="${raw:1:${#raw}-2}"
    elif [ "${raw:0:1}" = "'" ] && [ "${raw: -1}" = "'" ]; then
        raw="${raw:1:${#raw}-2}"
    fi
    [ -n "$raw" ] || return 1

    local IFS=':'
    read -ra REPOS <<<"$raw"

    local trimmed=()
    for part in "${REPOS[@]}"; do
        part="${part#"${part%%[![:space:]]*}"}"
        part="${part%"${part##*[![:space:]]}"}"
        [ -n "$part" ] && trimmed+=("$part")
    done
    REPOS=("${trimmed[@]}")
    [ "${#REPOS[@]}" -gt 0 ]
}

if ! _load_deploy_repos_from_env "$DEPLOY_ENV_FILE"; then
    echo "deploy: set DEPLOY_REPOS in $DEPLOY_ENV_FILE (colon-separated instance paths)." >&2
    echo "  Example: DEPLOY_REPOS=\"/root/club-voting-bot:/root/philo-club-bot\"" >&2
    exit 1
fi

unset _load_deploy_scripts_dir _load_deploy_repos_from_env
