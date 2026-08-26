#!/usr/bin/env python3
"""
check_bot_idle.py — report whether a bookclub_bot instance has seen any
non-admin activity recently, by reading its JSON activity file.

The bot writes this non-executable sidecar at most once every 30 seconds.

Usage:
    check_bot_idle.py <activity_json_file> <threshold_minutes>

Exit codes:
    0  IDLE    — no non-admin activity within the threshold
    1  ACTIVE  — non-admin activity within the threshold
    2  UNKNOWN — file missing arguments, unreadable, or unexpected contents

Always prints one line to stdout describing the result.
"""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path


def _activity_utc(raw: object) -> datetime:
    """Parse and normalize an ISO-8601 activity timestamp."""
    if not isinstance(raw, str):
        raise ValueError("last_non_admin_activity must be a string")
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        # Accept early JSON sidecars that may have used naive UTC.
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def main() -> int:
    if len(sys.argv) != 3:
        print(
            f"usage: {sys.argv[0]} <activity_json_file> <threshold_minutes>",
            file=sys.stderr,
        )
        return 2

    path = Path(sys.argv[1])
    threshold_minutes = float(sys.argv[2])

    if not path.exists():
        print("UNKNOWN (activity file does not exist yet)")
        return 2

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("activity file must contain a JSON object")
        last_activity = data.get("last_non_admin_activity")
    except Exception as e:
        print(f"UNKNOWN (could not read activity file: {e})")
        return 2

    if last_activity is None:
        print("UNKNOWN (activity timestamp is missing)")
        return 2

    try:
        last_activity = _activity_utc(last_activity)
    except (TypeError, ValueError) as e:
        print(f"UNKNOWN (invalid activity timestamp: {e})")
        return 2
    age_minutes = (datetime.now(UTC) - last_activity).total_seconds() / 60
    status = "ACTIVE" if age_minutes < threshold_minutes else "IDLE"
    print(
        f"{status} (last non-admin activity {age_minutes:.1f} min ago, "
        f"at {last_activity.astimezone(UTC):%Y-%m-%d %H:%M:%S} UTC)"
    )
    return 1 if status == "ACTIVE" else 0


if __name__ == "__main__":
    sys.exit(main())
