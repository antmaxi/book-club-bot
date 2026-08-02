"""
Tests for deploy/logs bash scripts (load_deploy_repos.sh, deploy_bots.sh, logs.sh).

These run real bash in subprocesses — no mocks of the shell logic.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
LOAD_DEPLOY_REPOS = SCRIPTS_DIR / "load_deploy_repos.sh"
DEPLOY_BOTS = SCRIPTS_DIR / "deploy_bots.sh"
LOGS_SH = SCRIPTS_DIR / "logs.sh"

SCRIPTS_AVAILABLE = (
    LOAD_DEPLOY_REPOS.is_file() and DEPLOY_BOTS.is_file() and LOGS_SH.is_file()
)
GIT_AVAILABLE = shutil.which("git") is not None


def _git_init_commit(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=test@test",
            "-c",
            "user.name=test",
            "commit",
            "--allow-empty",
            "-m",
            "init",
            "-q",
        ],
        cwd=path,
        check=True,
    )


def _source_repos(env_file: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["DEPLOY_ENV_FILE"] = str(env_file)
    return subprocess.run(
        [
            "bash",
            "-c",
            f'source "{LOAD_DEPLOY_REPOS}" && printf "%s\\n" "${{REPOS[@]}}"',
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _make_instance(parent: Path, name: str, *, with_log: bool = False) -> Path:
    inst = parent / name
    inst.mkdir(parents=True)
    (inst / "docker-compose.yml").write_text("services: {}\n")
    (inst / "data").mkdir()
    _git_init_commit(inst)
    if with_log:
        log_dir = inst / "logs"
        log_dir.mkdir()
        (log_dir / "bookclub_bot.log").write_text(
            "2026-01-01 12:00:00 - bookclub_bot - ERROR - deploy-script-test\n"
        )
    return inst


class TestLoadDeployRepos(unittest.TestCase):
    @unittest.skipUnless(SCRIPTS_AVAILABLE, "deploy scripts not present (mount scripts/)")
    def test_parses_double_quoted_deploy_repos(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_text('DEPLOY_REPOS="/data/a:/data/b"\n')
            proc = _source_repos(env_file)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(proc.stdout.splitlines(), ["/data/a", "/data/b"])

    @unittest.skipUnless(SCRIPTS_AVAILABLE, "deploy scripts not present (mount scripts/)")
    def test_parses_single_quoted_and_export_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_text("export DEPLOY_REPOS='/x:/y'\n")
            proc = _source_repos(env_file)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(proc.stdout.splitlines(), ["/x", "/y"])

    @unittest.skipUnless(SCRIPTS_AVAILABLE, "deploy scripts not present (mount scripts/)")
    def test_repos_alias_and_last_line_wins(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_text(
                "REPOS=/old/only\n"
                'DEPLOY_REPOS="/first:/second"\n'
                'DEPLOY_REPOS="/winner"\n'
            )
            proc = _source_repos(env_file)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(proc.stdout.splitlines(), ["/winner"])

    @unittest.skipUnless(SCRIPTS_AVAILABLE, "deploy scripts not present (mount scripts/)")
    def test_missing_deploy_repos_exits_with_message(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_text("BOT_TOKEN=abc\n")
            proc = _source_repos(env_file)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("DEPLOY_REPOS", proc.stderr)

    @unittest.skipUnless(SCRIPTS_AVAILABLE, "deploy scripts not present (mount scripts/)")
    def test_missing_env_file_exits_with_message(self) -> None:
        env_file = Path("/nonexistent/path/.env")
        proc = _source_repos(env_file)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("DEPLOY_REPOS", proc.stderr)


class TestDeployBotsScript(unittest.TestCase):
    def _run_check_only(self, env_file: Path) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["DEPLOY_ENV_FILE"] = str(env_file)
        return subprocess.run(
            ["bash", str(DEPLOY_BOTS), "--check-only"],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    @unittest.skipUnless(
        SCRIPTS_AVAILABLE and GIT_AVAILABLE, "needs deploy scripts and git"
    )
    def test_check_only_reports_configured_instance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inst = _make_instance(root, "club-a")
            env_file = root / ".env"
            env_file.write_text(f'DEPLOY_REPOS="{inst}"\n')
            proc = self._run_check_only(env_file)
            self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
            self.assertIn("== club-a ==", proc.stdout)
            self.assertIn(str(inst), proc.stdout)

    @unittest.skipUnless(SCRIPTS_AVAILABLE, "deploy scripts not present (mount scripts/)")
    def test_check_only_skips_missing_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env_file = root / ".env"
            missing = root / "no-such-bot"
            env_file.write_text(f'DEPLOY_REPOS="{missing}"\n')
            proc = self._run_check_only(env_file)
            self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
            self.assertIn("Summary", proc.stdout)
            self.assertIn("missing directory", proc.stdout)


class TestLogsScript(unittest.TestCase):
    def _run_logs(
        self, env_file: Path, *args: str
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["DEPLOY_ENV_FILE"] = str(env_file)
        return subprocess.run(
            ["bash", str(LOGS_SH), *args],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    @unittest.skipUnless(SCRIPTS_AVAILABLE, "deploy scripts not present (mount scripts/)")
    def test_help_exits_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_text('DEPLOY_REPOS="/tmp/x"\n')
            proc = self._run_logs(env_file, "--help")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("Usage", proc.stdout)

    @unittest.skipUnless(
        SCRIPTS_AVAILABLE and GIT_AVAILABLE, "needs deploy scripts and git"
    )
    def test_no_log_files_exits_one(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inst = _make_instance(root, "quiet-bot", with_log=False)
            env_file = root / ".env"
            env_file.write_text(f'DEPLOY_REPOS="{inst}"\n')
            proc = self._run_logs(env_file, "-e", "-n", "5")
            self.assertEqual(proc.returncode, 1)
            self.assertIn("No log files found", proc.stderr)

    @unittest.skipUnless(
        SCRIPTS_AVAILABLE and GIT_AVAILABLE, "needs deploy scripts and git"
    )
    def test_reads_error_line_from_instance_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inst = _make_instance(root, "loud-bot", with_log=True)
            env_file = root / ".env"
            env_file.write_text(f'DEPLOY_REPOS="{inst}"\n')
            proc = self._run_logs(env_file, "-e", "-n", "5")
            self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
            self.assertIn("[loud-bot]", proc.stdout)
            self.assertIn("deploy-script-test", proc.stdout)


if __name__ == "__main__":
    unittest.main()
