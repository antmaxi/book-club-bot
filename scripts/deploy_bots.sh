#!/bin/bash
#
# deploy_bots.sh — update one or more book-club-bot instances on this server:
# for each configured subfolder, check whether the bot has seen any non-admin
# activity recently, confirm with the operator, then stop the containers,
# git pull, and bring them back up rebuilt.
#
# The idle check reads ctx.bot_data["last_non_admin_activity"], which
# bookclub_bot.py's membership_gate() stamps on every update from a
# non-admin user (regardless of ALLOWED_CHAT_ID). Admin activity — e.g. the
# operator poking the bot to test the deploy — never counts as "in use", so
# running this script yourself doesn't block itself on the next run. See
# scripts/check_bot_idle.py for how the value is read.
#
# Usage:
#   ./deploy_bots.sh                    Interactive: prompt for every repo
#   ./deploy_bots.sh --yes              Auto-confirm IDLE repos; still prompt for ACTIVE/UNKNOWN
#   ./deploy_bots.sh --yes --skip-active   Fully unattended: update IDLE repos, skip ACTIVE/UNKNOWN silently (good for cron)
#   ./deploy_bots.sh --check-only       Print status for every repo and exit; no prompts, no changes
#   ./deploy_bots.sh --threshold 20     Consider "active" anything touched in the last 20 minutes (default: 10)
#
# Exit code is nonzero if any repo failed to come back up after being stopped.

set -uo pipefail

# --- Configuration ---------------------------------------------------------
# One subfolder per running instance. Each must be a git clone of this repo
# containing its own docker-compose.yml, .env, and data/ directory.
#
# This array is deliberately overridden from a *local, untracked* file
# instead of edited in place: this script lives inside a repo that gets
# `git pull`-ed by itself, and a server-specific path list would either get
# clobbered by the pull or turn into a permanent merge conflict. Create
# deploy_bots.local.sh next to this script (gitignored) and set REPOS there.
REPOS=(
    "/root/book-club-bot"
    "/root/philo-club-bot"
    "/root/test-club-bot"
)

IDLE_THRESHOLD_MINUTES=10
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IDLE_CHECKER="${SCRIPT_DIR}/check_bot_idle.py"
LOG_FILE="${SCRIPT_DIR}/deploy_bots.log"

LOCAL_CONFIG="${SCRIPT_DIR}/deploy_bots.local.sh"
if [ -f "$LOCAL_CONFIG" ]; then
    # shellcheck source=/dev/null
    source "$LOCAL_CONFIG"
fi

# --- Flags -------------------------------------------------------------
AUTO_YES=0        # --yes: don't prompt for IDLE repos
SKIP_ACTIVE=0     # --skip-active: don't prompt for ACTIVE/UNKNOWN repos either, just skip them
CHECK_ONLY=0      # --check-only: report and exit, touch nothing

while [ $# -gt 0 ]; do
    case "$1" in
        --yes|-y) AUTO_YES=1 ;;
        --skip-active) SKIP_ACTIVE=1 ;;
        --check-only) CHECK_ONLY=1 ;;
        --threshold) IDLE_THRESHOLD_MINUTES="$2"; shift ;;
        *) echo "Unknown argument: $1" >&2; exit 2 ;;
    esac
    shift
done

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a "$LOG_FILE"
}

confirm() {
    # confirm "prompt" "default(y|n)" -> 0 if the operator said yes
    local prompt="$1" default="$2" reply
    local hint="y/N"
    [ "$default" = "y" ] && hint="Y/n"
    read -r -p "$prompt [$hint] " reply
    reply="${reply:-$default}"
    [[ "$reply" =~ ^[Yy] ]]
}

UPDATED=()
SKIPPED=()
FAILED=()

process_repo() {
    local repo="$1"
    local name; name="$(basename "$repo")"

    if [ ! -d "$repo" ]; then
        log "[$name] SKIP — directory does not exist: $repo"
        SKIPPED+=("$name (missing directory)")
        return
    fi
    if [ ! -f "$repo/docker-compose.yml" ]; then
        log "[$name] SKIP — no docker-compose.yml in $repo"
        SKIPPED+=("$name (not a bot instance)")
        return
    fi
    if ! git -C "$repo" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        log "[$name] SKIP — not a git repository: $repo"
        SKIPPED+=("$name (not a git repo)")
        return
    fi

    # --- Idle check ---------------------------------------------------
    local persistence_file="$repo/data/bot_persistence"
    local status_line status_word
    status_line="$(python3 "$IDLE_CHECKER" "$persistence_file" "$IDLE_THRESHOLD_MINUTES")"
    status_word="${status_line%% *}"   # first word: IDLE / ACTIVE / UNKNOWN

    local running
    running="$(cd "$repo" && docker compose ps --status running -q 2>/dev/null | wc -l | tr -d ' ')"

    # Currently-deployed commit (HEAD before any pull): hash, commit date, subject.
    # Lets the operator see what version is running before deciding to update it.
    local head_info
    head_info="$(git -C "$repo" log -1 --format='%h  %cd  %s' --date=format:'%Y-%m-%d %H:%M' 2>/dev/null)"

    echo ""
    echo "== $name =="
    echo "  path:       $repo"
    echo "  containers: ${running} running"
    echo "  activity:   $status_line"
    echo "  commit:     ${head_info:-(unknown)}"

    if [ "$CHECK_ONLY" -eq 1 ]; then
        return
    fi

    # --- Decide whether to proceed -------------------------------------
    local proceed=0
    if [ "$status_word" = "IDLE" ]; then
        if [ "$AUTO_YES" -eq 1 ]; then
            proceed=1
        elif confirm "  Proceed with update for $name?" "y"; then
            proceed=1
        fi
    else
        # ACTIVE or UNKNOWN
        if [ "$SKIP_ACTIVE" -eq 1 ]; then
            log "[$name] SKIP — $status_word, --skip-active set"
            SKIPPED+=("$name ($status_word)")
            return
        fi
        echo "  WARNING: bot looks like it may currently be in use."
        if confirm "  Proceed with update for $name anyway?" "n"; then
            proceed=1
        fi
    fi

    if [ "$proceed" -ne 1 ]; then
        log "[$name] SKIP — declined ($status_word)"
        SKIPPED+=("$name (declined, $status_word)")
        return
    fi

    # --- Refuse to touch a repo with local edits the pull would clobber -
    if [ -n "$(git -C "$repo" status --porcelain)" ]; then
        log "[$name] SKIP — working tree has uncommitted changes, refusing to pull"
        SKIPPED+=("$name (dirty working tree)")
        return
    fi

    log "[$name] Stopping containers..."
    if ! (cd "$repo" && docker compose stop) >>"$LOG_FILE" 2>&1; then
        log "[$name] FAILED — docker compose stop failed"
        FAILED+=("$name (stop failed)")
        return
    fi

    log "[$name] Pulling latest code..."
    if ! git -C "$repo" pull >>"$LOG_FILE" 2>&1; then
        log "[$name] FAILED — git pull failed, restarting previous containers"
        (cd "$repo" && docker compose up -d) >>"$LOG_FILE" 2>&1
        FAILED+=("$name (git pull failed)")
        return
    fi

    log "[$name] Rebuilding and starting containers..."
    if ! (cd "$repo" && docker compose up -d --build) >>"$LOG_FILE" 2>&1; then
        log "[$name] FAILED — docker compose up --build failed; bot may be DOWN, check manually"
        FAILED+=("$name (rebuild failed — check manually)")
        return
    fi

    log "[$name] Updated successfully."
    UPDATED+=("$name")
}

log "===== deploy_bots.sh starting (threshold=${IDLE_THRESHOLD_MINUTES}m, repos=${#REPOS[@]}) ====="

for repo in "${REPOS[@]}"; do
    process_repo "$repo"
done

echo ""
echo "===== Summary ====="
echo "Updated: ${#UPDATED[@]}  ${UPDATED[*]:-}"
echo "Skipped: ${#SKIPPED[@]}  ${SKIPPED[*]:-}"
echo "Failed:  ${#FAILED[@]}  ${FAILED[*]:-}"

[ "${#FAILED[@]}" -eq 0 ]
