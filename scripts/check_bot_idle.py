#!/usr/bin/env python3
"""
check_bot_idle.py — report whether a bookclub_bot instance has seen any
non-admin activity recently, by reading its PicklePersistence file directly.

bookclub_bot.py's membership_gate() stamps ctx.bot_data["last_non_admin_activity"]
on every update from a non-admin user, regardless of ALLOWED_CHAT_ID. That field
is what this script reads.

No python-telegram-bot dependency needed: PicklePersistence writes plain
Python objects here (see bookclub_bot.py's ctx.user_data / ctx.bot_data
usage — strings, ints, datetimes), so a stdlib pickle.load() is sufficient.
python-telegram-bot's own reader (_BotUnpickler) is only required when the
graph contains an actual telegram.Bot/TelegramObject instance, which this
bot never stores.

Usage:
    check_bot_idle.py <persistence_file> <threshold_minutes>

Exit codes:
    0  IDLE    — no non-admin activity within the threshold (or ever)
    1  ACTIVE  — non-admin activity within the threshold
    2  UNKNOWN — file missing arguments, unreadable, or unexpected contents

Always prints one line to stdout describing the result.
"""

import pickle
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _activity_utc(dt: datetime) -> datetime:
    """Normalize persisted activity timestamps for age comparison."""
    if dt.tzinfo is None:
        # Legacy pickles stored naive local/UTC times without tzinfo.
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def main() -> int:
    if len(sys.argv) != 3:
        print(
            f"usage: {sys.argv[0]} <persistence_file> <threshold_minutes>",
            file=sys.stderr,
        )
        return 2

    path = Path(sys.argv[1])
    threshold_minutes = float(sys.argv[2])

    if not path.exists():
        print(
            "IDLE (no persistence file yet — bot never ran, or this is a fresh instance)"
        )
        return 0

    try:
        with path.open("rb") as f:
            data: Any = pickle.load(f)
        # bot_data is pickled as literal None (not simply absent) when no
        # non-admin has ever interacted with this instance — .get(key, {})
        # alone doesn't catch that, since the key IS present, just null.
        bot_data = data.get("bot_data") or {}
        last_activity = bot_data.get("last_non_admin_activity")
    except Exception as e:
        print(f"UNKNOWN (could not read persistence file: {e})")
        return 2

    if last_activity is None:
        print("IDLE (no non-admin activity recorded yet)")
        return 0

    last_activity = _activity_utc(last_activity)
    age_minutes = (datetime.now(UTC) - last_activity).total_seconds() / 60
    status = "ACTIVE" if age_minutes < threshold_minutes else "IDLE"
    print(
        f"{status} (last non-admin activity {age_minutes:.1f} min ago, "
        f"at {last_activity.astimezone(UTC):%Y-%m-%d %H:%M:%S} UTC)"
    )
    return 1 if status == "ACTIVE" else 0


if __name__ == "__main__":
    sys.exit(main())
