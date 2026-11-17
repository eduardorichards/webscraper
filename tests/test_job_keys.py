"""Tests for job keys shared by LinkedIn and ATS sources (utils/job_keys.py)."""

import unittest

from utils.job_keys import (is_linkedin_key, is_valid_key, job_url_for, make_key,
                            source_of)


class TestJobKeys(unittest.TestCase):

    def test_make_key(self):
        self.assertEqual(make_key('greenhouse', 'gitlab', 8638232002),
                         'greenhouse:gitlab:8638232002')
        self.assertEqual(make_key('ashby', 'kraken.com', '993557d9-7482'),
                         'ashby:kraken.com:993557d9-7482')
        self.assertEqual(make_key('lever', 'Allata', 'f035d332'), 'lever:Allata:f035d332')

    def test_make_key_rejects_bad_parts(self):
        with self.assertRaises(ValueError):
            make_key('linkedin', 'x', '1')
        with self.assertRaises(ValueError):
            make_key('lever', 'bad slug', '1')
        with self.assertRaises(ValueError):
            make_key('lever', 'redbee', 'a:b')

    def test_source_of(self):
        self.assertEqual(source_of('4312345678'), 'linkedin')
        self.assertEqual(source_of('greenhouse:gitlab:1'), 'greenhouse')
        self.assertEqual(source_of('lever:redbee:f035d332-b86e'), 'lever')
        self.assertEqual(source_of('ashby:kraken.com:abc'), 'ashby')
        self.assertIsNone(source_of('monster:x:1'))
        self.assertIsNone(source_of(''))

    def test_is_linkedin_key(self):
        self.assertTrue(is_linkedin_key('4312345678'))
        self.assertTrue(is_linkedin_key('12345'))   # historical short IDs
        self.assertFalse(is_linkedin_key('lever:redbee:1'))
        self.assertFalse(is_linkedin_key(''))
        self.assertFalse(is_linkedin_key(None))

    def test_is_valid_key(self):
        self.assertTrue(is_valid_key('4312345678'))
        self.assertTrue(is_valid_key('ashby:kraken.com:993557d9-7482'))
        for bad in ('', '３００１', 'lever:redbee', 'lever:redbee:1;DROP', 'x:y:z', '12a'):
            self.assertFalse(is_valid_key(bad), bad)

    def test_job_url_for(self):
        self.assertEqual(job_url_for('4312345678'),
                         'https://www.linkedin.com/jobs/view/4312345678/')
        # LinkedIn URL always built from the ID, even if a URL is stored
        self.assertEqual(job_url_for('4312345678', 'https://example.com'),
                         'https://www.linkedin.com/jobs/view/4312345678/')
        self.assertEqual(job_url_for('lever:redbee:1', 'https://jobs.lever.co/redbee/1'),
                         'https://jobs.lever.co/redbee/1')
        self.assertIsNone(job_url_for('lever:redbee:1'))
        self.assertIsNone(job_url_for('lever:redbee:1', 'javascript:alert(1)'))


if __name__ == '__main__':
    unittest.main()
