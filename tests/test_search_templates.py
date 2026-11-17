"""Consistency checks for SEARCH_TEMPLATES in config/settings.py."""

import unittest

from config.settings import SEARCH_TEMPLATES, TIME_POSTED_MAPPING
from scraper.models.search_config import SearchConfig


class TestSearchTemplates(unittest.TestCase):

    def test_names_are_unique(self):
        names = [t["name"] for t in SEARCH_TEMPLATES]
        self.assertEqual(len(names), len(set(names)))

    def test_each_group_runs_in_argentina_and_latam_remote(self):
        for ar, latam in zip(SEARCH_TEMPLATES[::2], SEARCH_TEMPLATES[1::2]):
            self.assertTrue(ar["name"].endswith(" AR"), ar["name"])
            self.assertEqual(latam["name"], ar["name"][:-len(" AR")] + " LATAM")
            self.assertEqual(ar["keywords"], latam["keywords"])
            self.assertEqual((ar["location"], ar["remote"]), ("Argentina", False))
            self.assertEqual((latam["location"], latam["remote"]), ("Latin America", True))
        self.assertEqual(len(SEARCH_TEMPLATES) % 2, 0)

    def test_requests_all_target_levels(self):
        # Associate (3) is in TARGET_SENIORITY_LEVELS, so it must be requested too
        for t in SEARCH_TEMPLATES:
            self.assertEqual(t["experience_levels"], [1, 2, 3], t["name"])

    def test_window_overlaps_hourly_cron(self):
        # The cron runs hourly; a 2h window covers a late or skipped run
        for t in SEARCH_TEMPLATES:
            self.assertEqual(t["time_posted"], "2h", t["name"])

    def test_no_boolean_operators(self):
        # The logged-out search doesn't honor OR (see config/settings.py)
        for t in SEARCH_TEMPLATES:
            self.assertNotIn(" OR ", t["keywords"], t["name"])
            self.assertNotIn('"', t["keywords"], t["name"])

    def test_templates_build_a_search_config(self):
        for t in SEARCH_TEMPLATES:
            params = dict(t)
            params.pop("name")
            self.assertIn(params["time_posted"], TIME_POSTED_MAPPING)
            SearchConfig(**params)


if __name__ == '__main__':
    unittest.main()
