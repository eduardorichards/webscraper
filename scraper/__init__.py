"""
Job Scraper Package

A modular job scraping application for extracting job listings
from various job boards including LinkedIn.
"""

__version__ = "1.1.0"
__author__ = "Eduardo"

from .core.scraper import JobScraper
from .core.detail_scraper import DetailScraper
from .core.keyword_matcher import KeywordMatcher
from .models.search_config import SearchConfig
from .models.job import Job
from .models.keyword_config import KeywordConfig
from .models.match_result import MatchResult
from .analyzers.keyword_analyzer import KeywordAnalyzer

__all__ = [
    'JobScraper',
    'DetailScraper',
    'KeywordMatcher',
    'SearchConfig',
    'Job',
    'KeywordConfig',
    'MatchResult',
    'KeywordAnalyzer',
]