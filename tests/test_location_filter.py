"""Tests for the ATS location filter (utils/location_filter.py)."""

import unittest

from utils.location_filter import allowed_location, check_location, is_us_only


class TestAllowedLocation(unittest.TestCase):

    def test_allowlist_terms(self):
        for text in ('Argentina', 'Buenos Aires, Argentina', 'CABA', 'Capital Federal',
                     'Remote - LATAM', 'Latin America', 'Latinoamérica', 'South America',
                     'Remote, Americas', 'AMER', 'Remote (AMER)', 'Anywhere',
                     'Worldwide', 'Remote - Global', 'Anywhere in LATAM',
                     'Anywhere in Argentina'):
            self.assertTrue(allowed_location(text), text)

    def test_other_places(self):
        for text in ('Remote - US', 'United States', 'US only', 'Canada',
                     'Remote, Poland', 'North America', 'San Francisco, CA', 'London',
                     'Globant HQ', 'Americana, Brazil', 'Anywhere in the United States',
                     'Anywhere in Ireland', ''):
            self.assertFalse(allowed_location(text), text)


class TestCheckLocation(unittest.TestCase):

    def assertKeep(self, locations, description=None, is_remote=False):
        keep, reason = check_location(locations, description, is_remote)
        self.assertTrue(keep, (locations, reason))

    def assertDrop(self, locations, description=None, is_remote=False):
        keep, reason = check_location(locations, description, is_remote)
        self.assertFalse(keep, (locations, reason))

    def test_keep_allowed(self):
        self.assertKeep(['Buenos Aires'])
        self.assertKeep(['Remote, LATAM'])
        self.assertKeep(['AMER'], is_remote=True)

    def test_any_location_counts(self):
        # Kraken lists Argentina only as a secondary location
        self.assertKeep(['Brazil', 'Peru', 'Argentina', 'Mexico'], is_remote=True)
        self.assertKeep(['New York', 'Buenos Aires'])

    def test_allowlist_wins_over_us_phrases(self):
        self.assertKeep(['Argentina'], 'Must reside in the US.')

    def test_drop_country_only_remote(self):
        self.assertDrop(['Remote - US'], is_remote=True)
        self.assertDrop(['United States'], is_remote=True)
        self.assertDrop(['US only'])
        self.assertDrop(['Canada'], is_remote=True)
        self.assertDrop(['Remote, Canada', 'Remote, United States'], is_remote=True)

    def test_drop_other_cities(self):
        self.assertDrop(['San Francisco, CA'])
        self.assertDrop(['Kyiv', 'Lviv'])
        self.assertDrop(['Bogota', 'Lima'])

    def test_bare_remote_kept(self):
        self.assertKeep(['Remote'], 'Python and Go. We hire across time zones.')
        self.assertKeep(['Fully Remote'])
        self.assertKeep([], 'Work from wherever.', is_remote=True)

    def test_bare_remote_us_only_dropped(self):
        for description in (
                'You must be based in the US.',
                'This is a US-based role.',
                'Open to U.S. only.',
                'United States only.',
                'Candidates must be authorized to work in the United States.',
                'You must reside in the US.',
                'Applicants must live in the U.S.'):
            self.assertDrop(['Remote'], description)
            self.assertDrop([], description, is_remote=True)

    def test_no_location_not_remote_dropped(self):
        self.assertDrop([], 'Anything.', is_remote=False)

    def test_us_only_phrases(self):
        self.assertTrue(is_us_only('Must be US-based'))
        self.assertFalse(is_us_only('We sell to customers in the US and LATAM.'))
        self.assertFalse(is_us_only('based in the USSR museum'))
        self.assertFalse(is_us_only(None))


if __name__ == '__main__':
    unittest.main()
