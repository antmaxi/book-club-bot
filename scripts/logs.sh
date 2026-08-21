#!/bin/bash
#
# logs.sh — search and tail logs across every club-voting-bot instance on this
# server from one place, so you don't have to grep three separate files by hand
# when something breaks.
#
# It reads each instance's logs/bookclub_bot.log (plus its rotated .1/.2/.3
# backups) and prefixes every line with the instance name, so you can tell which
# bot a message came from. Colours ERROR/CRITICAL red and WARNING yellow.
#
# Instance list: same DEPLOY_REPOS in the project root .env as deploy_bots.sh
# (see scripts/load_deploy_repos.sh).
#
# Usage:
#   ./logs.sh                      Last 50 ERROR/WARNING lines across all bots
#   ./logs.sh -e                   Only ERROR/CRITICAL
#   ./logs.sh -l INFO              Only lines at a given level
#   ./logs.sh -g "notify_new"      Only lines matching a regex
#   ./logs.sh -a                   All lines (no level filter)
#   ./logs.sh -n 200               Show up to 200 matching lines (default 50)
#   ./logs.sh -b philo             Restrict to instances whose name matches "philo"
#   ./logs.sh --today              Only today's lines
#   ./logs.sh -f                   Follow (tail -F) the live logs, ERROR/WARNING
#   ./logs.sh -f -a                Follow everything
#
# Flags combine: `./logs.sh -e -b philo -n 100` = last 100 errors from philo-*.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=load_deploy_repos.sh
source "${SCRIPT_DIR}/load_deploy_repos.sh"

LOG_RELPATH="logs/bookclub_bot.log"

# --- Defaults / flags ------------------------------------------------------
LEVEL_FILTER="WARN"   # WARN = ERROR+WARNING (the default); ALL = no filter
GREP_PATTERN=""
LINES=50
BOT_MATCH=""
FOLLOW=0
TODAY_ONLY=0

usage() { sed -n '2,/^set /{/^set /d;p}' "$0" | sed 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
    case "$1" in
        -e|--errors)   LEVEL_FILTER="ERROR" ;;
        -a|--all)      LEVEL_FILTER="ALL" ;;
        -l|--level)    LEVEL_FILTER="$(echo "$2" | tr '[:lower:]' '[:upper:]')"; shift ;;
        -g|--grep)     GREP_PATTERN="$2"; shift ;;
        -n|--lines)    LINES="$2"; shift ;;
        -b|--bot)      BOT_MATCH="$2"; shift ;;
        -f|--follow)   FOLLOW=1 ;;
        --today)       TODAY_ONLY=1 ;;
        -h|--help)     usage; exit 0 ;;
        *) echo "Unknown argument: $1" >&2; echo "Try: $0 --help" >&2; exit 2 ;;
    esac
    shift
done

# Level filter -> extended regex matched against the " - LEVEL - " field.
case "$LEVEL_FILTER" in
    ALL)   LEVEL_RE="" ;;
    WARN)  LEVEL_RE=" - (ERROR|CRITICAL|WARNING) - " ;;
    ERROR) LEVEL_RE=" - (ERROR|CRITICAL) - " ;;
    *)     LEVEL_RE=" - ${LEVEL_FILTER} - " ;;
esac

# --- Collect the log files for the selected instances ----------------------
declare -a NAMES FILES
for repo in "${REPOS[@]}"; do
    name="$(basename "$repo")"
    if [ -n "$BOT_MATCH" ] && [[ "$name" != *"$BOT_MATCH"* ]]; then
        continue
    fi
    base="$repo/$LOG_RELPATH"
    # Current log first, then rotated backups oldest->newest so time runs forward.
    for f in "$base.3" "$base.2" "$base.1" "$base"; do
        [ -f "$f" ] && { NAMES+=("$name"); FILES+=("$f"); }
    done
done

# ${FILES[*]:-} is empty iff no files matched — and, unlike ${#FILES[@]}, it
# doesn't trip `set -u` on an as-yet-empty array in older/stricter bash.
if [ -z "${FILES[*]:-}" ]; then
    echo "No log files found." >&2
    if [ -n "$BOT_MATCH" ]; then echo "(filter: -b '$BOT_MATCH')" >&2; fi
    echo "Checked instances: ${REPOS[*]}" >&2
    exit 1
fi

# Unbuffered passthrough. Used instead of `cat` inside the pipeline so
# -f/--follow streams each line the moment it's written rather than waiting for
# a 4 KB block to fill. `sed -u ''` (empty script = print unchanged) reads and
# writes unbuffered; `cat` and mawk both block-buffer pipe input and would
# stall the live tail until a full block accumulates.
_pass() { sed -u ''; }

# --- Highlight levels (only when writing to a terminal) --------------------
colorize() {
    if [ -t 1 ]; then
        # -u so colours stream line-by-line under --follow to a terminal.
        sed -u -E $'s/( - (ERROR|CRITICAL) - )/\033[31m\\1\033[0m/; s/( - WARNING - )/\033[33m\\1\033[0m/'
    else
        _pass
    fi
}

filter_chain() {
    # stdin: prefixed log lines. Applies level, today, and grep filters in turn.
    if [ -n "$LEVEL_RE" ]; then
        grep -E --line-buffered "$LEVEL_RE"
    else
        _pass
    fi | {
        if [ "$TODAY_ONLY" -eq 1 ]; then
            grep -F --line-buffered "$(date '+%Y-%m-%d')"
        else
            _pass
        fi
    } | {
        if [ -n "$GREP_PATTERN" ]; then
            grep -E --line-buffered "$GREP_PATTERN"
        else
            _pass
        fi
    }
}

if [ "$FOLLOW" -eq 1 ]; then
    # Follow only the *current* log of each selected instance.
    declare -a CUR_NAMES CUR_FILES
    for i in "${!FILES[@]}"; do
        case "${FILES[$i]}" in
            *.1|*.2|*.3) continue ;;
        esac
        CUR_NAMES+=("${NAMES[$i]}"); CUR_FILES+=("${FILES[$i]}")
    done
    echo "Following ${#CUR_FILES[@]} log(s) — Ctrl-C to stop:" >&2
    printf '  %s\n' "${CUR_FILES[@]}" >&2
    echo "" >&2
    # One `tail | sed` per file, each prefixing its own lines, all merged into
    # the group's stdout. This is deliberately NOT a single multi-file `tail -F`
    # piped through an awk that parses the "==> file <==" separators: that path
    # buffers unpredictably (the awk stalls waiting for a full input block), so
    # nothing shows until the pipe closes. `sed -u` keeps each stream unbuffered.
    trap 'kill 0 2>/dev/null' EXIT INT TERM
    {
        for i in "${!CUR_FILES[@]}"; do
            tail -n 0 -F "${CUR_FILES[$i]}" 2>/dev/null \
                | sed -u "s|^|[${CUR_NAMES[$i]}] |" &
        done
        wait
    } | filter_chain | colorize
    exit 0
fi

# --- One-shot search: prefix each file's lines, filter, keep the last N -----
for i in "${!FILES[@]}"; do
    awk -v tag="[${NAMES[$i]}] " '{ print tag $0 }' "${FILES[$i]}"
done \
    | filter_chain \
    | tail -n "$LINES" \
    | colorize
