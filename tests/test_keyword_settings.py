"""Consistency checks for config/keyword_settings.py."""

import unittest

from config.keyword_settings import DEFAULT_KEYWORDS, WEIGHTED_KEYWORDS


class TestKeywordSettings(unittest.TestCase):

    def test_every_weight_matches_a_keyword(self):
        # Weights are looked up by exact keyword, so a key with different case
        # or a phrase missing from DEFAULT_KEYWORDS never takes effect.
        unmatched = sorted(set(WEIGHTED_KEYWORDS) - set(DEFAULT_KEYWORDS))
        self.assertEqual(unmatched, [])

    def test_keywords_are_unique_ignoring_case(self):
        lowered = [kw.lower() for kw in DEFAULT_KEYWORDS]
        duplicates = sorted({kw for kw in lowered if lowered.count(kw) > 1})
        self.assertEqual(duplicates, [])


if __name__ == '__main__':
    unittest.main()
