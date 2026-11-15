"""Tests for the "above my level" seniority rule."""

import unittest

from config.settings import SENIORITY_ORDER, TARGET_SENIORITY_LEVELS
from utils.seniority import levels_above
from utils.sqlite_storage import SQLiteStorage


class TestLevelsAbove(unittest.TestCase):

    def test_order_matches_linkedin_values(self):
        self.assertEqual(SENIORITY_ORDER, ["Internship", "Entry level", "Associate",
                                           "Mid-Senior level", "Director", "Executive"])

    def test_default_targets(self):
        self.assertEqual(TARGET_SENIORITY_LEVELS, ["Internship", "Entry level", "Associate"])
        self.assertEqual(SQLiteStorage.ABOVE_TARGET_LEVELS,
                         ["Mid-Senior level", "Director", "Executive"])

    def test_highest_target_wins(self):
        self.assertEqual(levels_above(["Entry level"]),
                         ["Associate", "Mid-Senior level", "Director", "Executive"])
        self.assertEqual(levels_above(["Internship", "Director"]), ["Executive"])
        self.assertEqual(levels_above(["Executive"]), [])

    def test_empty_targets_hide_nothing(self):
        self.assertEqual(levels_above([]), [])

    def test_unknown_target_rejected(self):
        with self.assertRaisesRegex(ValueError, "Senior"):
            levels_above(["Senior"])


if __name__ == '__main__':
    unittest.main()
