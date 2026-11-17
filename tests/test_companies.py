"""Tests for the ATS company list: data file and companies table sync."""

import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from utils.companies import COMPANIES_FILE, load_companies
from utils.sqlite_storage import SQLiteStorage

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _write_file(path, companies):
    Path(path).write_text(json.dumps({"companies": companies}), encoding="utf-8")


class TestDataFile(unittest.TestCase):

    def test_shipped_file_is_valid(self):
        entries = load_companies()
        self.assertEqual(COMPANIES_FILE, PROJECT_ROOT / "config" / "companies.json")
        boards = {(e["ats"], e["slug"]): e for e in entries}
        self.assertEqual(len(entries), 18)
        self.assertEqual(sum(e["ats"] == "greenhouse" for e in entries), 5)
        self.assertEqual(sum(e["ats"] == "lever" for e in entries), 7)
        self.assertEqual(sum(e["ats"] == "ashby" for e in entries), 6)
        # Moved from Greenhouse to Ashby (Greenhouse: empty board / 404)
        self.assertEqual(boards[("ashby", "webflow")]["name"], "Webflow")
        self.assertEqual(boards[("ashby", "stensul")]["name"], "Stensul")
        self.assertNotIn(("greenhouse", "webflow"), boards)
        self.assertNotIn(("greenhouse", "stensul"), boards)
        self.assertEqual(boards[("lever", "tryjeeves")]["name"], "Jeeves")
        self.assertEqual(boards[("ashby", "kraken.com")]["name"], "Kraken")
        self.assertTrue(all(e["active"] for e in entries))

    def test_invalid_files_are_rejected(self):
        cases = [
            ([{"name": "A", "ats": "workday", "slug": "a"}], "unknown ats"),
            ([{"name": "A", "ats": "lever", "slug": "a b"}], "invalid slug"),
            ([{"name": " ", "ats": "lever", "slug": "a"}], "without a name"),
            ([{"name": "A", "ats": "lever", "slug": "a"},
              {"name": "A", "ats": "lever", "slug": "b"}], "duplicated company"),
            ([{"name": "A", "ats": "lever", "slug": "a"},
              {"name": "B", "ats": "lever", "slug": "a"}], "duplicated board"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "c.json"
            for companies, message in cases:
                _write_file(path, companies)
                with self.assertRaisesRegex(ValueError, message):
                    load_companies(path)


class TestCompaniesSync(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp.name, "jobs.db")
        self.file = os.path.join(self.tmp.name, "companies.json")

    def tearDown(self):
        self.tmp.cleanup()

    def _open(self):
        with redirect_stdout(StringIO()):
            return SQLiteStorage(db_file=self.db_path, companies_file=self.file)

    def _rows(self):
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            "SELECT name, ats, slug, notes, active, last_checked_at,"
            " last_job_count FROM companies ORDER BY name").fetchall()
        conn.close()
        return rows

    def test_sync_keeps_check_stats(self):
        _write_file(self.file, [{"name": "Kraken", "ats": "ashby", "slug": "kraken.com"},
                                {"name": "redbee", "ats": "lever", "slug": "redbee"}])
        storage = self._open()
        storage.mark_company_checked("Kraken", 95)
        checked_at = self._rows()[0][5]
        self.assertRegex(checked_at, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

        # Re-init with the same file, then with changed config fields
        self._open()
        _write_file(self.file, [{"name": "Kraken", "ats": "ashby", "slug": "kraken.com",
                                 "notes": "AR as secondary location", "active": False},
                                {"name": "redbee", "ats": "lever", "slug": "redbee"}])
        self._open()
        self.assertEqual(self._rows(), [
            ("Kraken", "ashby", "kraken.com", "AR as secondary location", 0,
             checked_at, 95),
            ("redbee", "lever", "redbee", None, 1, None, None),
        ])

    def test_sync_company_moved_to_another_ats(self):
        _write_file(self.file, [{"name": "Webflow", "ats": "greenhouse", "slug": "webflow"}])
        storage = self._open()
        storage.mark_company_checked("Webflow", 0)
        checked_at = self._rows()[0][5]
        _write_file(self.file, [{"name": "Webflow", "ats": "ashby", "slug": "webflow",
                                 "notes": "moved"}])
        storage = self._open()
        self.assertEqual(self._rows(),
                         [("Webflow", "ashby", "webflow", "moved", 1, checked_at, 0)])
        self.assertEqual([(c["ats"], c["slug"]) for c in storage.get_companies()],
                         [("ashby", "webflow")])

    def test_sync_adds_and_removes(self):
        _write_file(self.file, [{"name": "A", "ats": "lever", "slug": "a"},
                                {"name": "B", "ats": "greenhouse", "slug": "b"}])
        self._open()
        _write_file(self.file, [{"name": "B", "ats": "greenhouse", "slug": "b"},
                                {"name": "C", "ats": "ashby", "slug": "c"}])
        storage = self._open()
        self.assertEqual([r[:3] for r in self._rows()],
                         [("B", "greenhouse", "b"), ("C", "ashby", "c")])
        self.assertEqual([c["name"] for c in storage.get_companies()], ["B", "C"])

    def test_get_companies_active_only(self):
        _write_file(self.file, [{"name": "A", "ats": "lever", "slug": "a", "active": False},
                                {"name": "B", "ats": "lever", "slug": "b"}])
        storage = self._open()
        self.assertEqual([c["name"] for c in storage.get_companies()], ["B"])
        self.assertEqual([c["name"] for c in storage.get_companies(active_only=False)],
                         ["A", "B"])


if __name__ == "__main__":
    unittest.main()
