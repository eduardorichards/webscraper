"""Tests for run_scraper.sh (the cron wrapper): argument forwarding, log lines
and the shared lock. Runs the script in a temp project dir with a fake
virtualenv and a fake main.py that only records its arguments."""

import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

FAKE_MAIN = textwrap.dedent("""\
    import json, sys
    print("FAKE_MAIN_ARGS=" + json.dumps(sys.argv[1:]))
""")


@unittest.skipUnless(shutil.which("bash"), "bash not available")
class TestRunScraper(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name)
        shutil.copy(str(PROJECT_ROOT / "run_scraper.sh"), str(self.project / "run_scraper.sh"))
        (self.project / "main.py").write_text(FAKE_MAIN)
        bin_dir = self.project / "venv" / "bin"
        bin_dir.mkdir(parents=True)
        os.symlink(sys.executable, str(bin_dir / "python"))
        (bin_dir / "activate").write_text('export PATH="%s:$PATH"\n' % bin_dir)
        self.log_dir = self.project / "logs"

    def _run(self, *args):
        env = dict(os.environ, LOG_DIR=str(self.log_dir))
        result = subprocess.run(["bash", str(self.project / "run_scraper.sh")] + list(args),
                                env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                universal_newlines=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        return (self.log_dir / "cron.log").read_text()

    def test_forwards_arguments_and_logs_them(self):
        log = self._run("--source", "ats")
        self.assertIn('FAKE_MAIN_ARGS=["--source", "ats"]', log)
        self.assertIn("- Starting scraper run (--source ats)\n", log)
        self.assertIn("- Scraper run finished (--source ats)\n", log)
        self.assertFalse((self.log_dir / "scraper.lock").exists())

    def test_no_arguments_unchanged(self):
        log = self._run()
        self.assertIn("FAKE_MAIN_ARGS=[]", log)
        self.assertIn("- Starting scraper run\n", log)
        self.assertIn("- Scraper run finished\n", log)

    def test_live_lock_skips_run(self):
        # Any run (LinkedIn or ATS) holding the shared lock makes the other skip
        self.log_dir.mkdir()
        (self.log_dir / "scraper.lock").write_text("%d\n" % os.getpid())
        log = self._run("--source", "ats")
        self.assertIn("Scraper already running (PID %d), skipping run (--source ats)."
                      % os.getpid(), log)
        self.assertNotIn("FAKE_MAIN_ARGS", log)
        self.assertNotIn("Starting scraper run", log)
        # The other run's lock is left alone
        self.assertEqual((self.log_dir / "scraper.lock").read_text().strip(), str(os.getpid()))

    def test_stale_lock_is_replaced(self):
        self.log_dir.mkdir()
        dead = subprocess.Popen([sys.executable, "-c", "pass"])
        dead.wait()
        (self.log_dir / "scraper.lock").write_text("%d\n" % dead.pid)
        log = self._run("--source", "ats")
        self.assertIn("Stale lock file found, removing.", log)
        self.assertIn('FAKE_MAIN_ARGS=["--source", "ats"]', log)


if __name__ == "__main__":
    unittest.main()
