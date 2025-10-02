"""Basic tests for the job scraper"""

import unittest
from scraper.models.job import Job
from scraper.models.search_config import SearchConfig
from scraper.core.url_builder import LinkedInURLBuilder


class TestJobScraper(unittest.TestCase):
    """Test cases for job scraper functionality"""
    
    def test_job_creation(self):
        """Test Job model creation"""
        job = Job(
            title="Python Developer",
            company="Tech Corp",
            location="Remote",
            work_modality="Remote",
            posted_date="1 day ago",
            job_url="https://example.com/job"
        )
        
        self.assertEqual(job.title, "Python Developer")
        self.assertEqual(job.company, "Tech Corp")
        self.assertEqual(job.work_modality, "Remote")
    
    def test_search_config_creation(self):
        """Test SearchConfig model creation"""
        config = SearchConfig(
            keywords="python",
            location="US",
            time_posted="1w",
            remote=True
        )
        
        self.assertEqual(config.keywords, "python")
        self.assertEqual(config.location, "US")
        self.assertTrue(config.remote)
        self.assertTrue(config.is_valid())
    
    def test_url_builder(self):
        """Test LinkedIn URL builder"""
        config = SearchConfig(
            keywords="java developer",
            location="Argentina",
            time_posted="24h",
            remote=False
        )
        
        url = LinkedInURLBuilder.build_search_url(config)
        
        self.assertIn("linkedin.com", url)
        self.assertIn("keywords=", url)
        self.assertIn("location=", url)
        self.assertIn("f_TPR=", url)


if __name__ == '__main__':
    unittest.main()