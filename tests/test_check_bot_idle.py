"""Tests for scripts/check_bot_idle.py."""

from __future__ import annotations

import pickle
import subprocess
import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "check_bot_idle.py"


class TestCheckBotIdle(unittest.TestCase):
    def _run(self, path: Path, threshold: float = 5) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(path), str(threshold)],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_aware_utc_timestamp_does_not_crash(self):
        with self.subTest("aware"):
            p = self._tmp_pickle(
                {"bot_data": {"last_non_admin_activity": datetime.now(UTC)}}
            )
            result = self._run(p)
            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn("ACTIVE", result.stdout)

    def test_legacy_naive_timestamp_does_not_crash(self):
        p = self._tmp_pickle(
            {
                "bot_data": {
                    "last_non_admin_activity": datetime.now(UTC).replace(tzinfo=None)
                }
            }
        )
        result = self._run(p)
        self.assertIn(result.returncode, (0, 1), result.stdout)

    def test_old_activity_is_idle(self):
        p = self._tmp_pickle(
            {
                "bot_data": {
                    "last_non_admin_activity": datetime.now(UTC) - timedelta(hours=1)
                }
            }
        )
        result = self._run(p, threshold=5)
        self.assertEqual(result.returncode, 0)
        self.assertIn("IDLE", result.stdout)

    def _tmp_pickle(self, data: dict) -> Path:
        import tempfile

        fd, name = tempfile.mkstemp(suffix=".pickle")
        path = Path(name)
        with path.open("wb") as f:
            pickle.dump(data, f)
        self.addCleanup(path.unlink, missing_ok=True)
        return path


if __name__ == "__main__":
    unittest.main()
