"""
Job Scraper Package

A modular job scraping application for extracting job listings 
from various job boards including LinkedIn.
"""

__version__ = "1.0.0"
__author__ = "Eduardo"

from .core.scraper import JobScraper
from .models.search_config import SearchConfig
from .models.job import Job

__all__ = ['JobScraper', 'SearchConfig', 'Job']