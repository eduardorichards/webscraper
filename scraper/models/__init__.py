"""Data models for job scraping"""
from .job import Job
from .search_config import SearchConfig
from .keyword_config import KeywordConfig
from .match_result import MatchResult

__all__ = ['Job', 'SearchConfig', 'KeywordConfig', 'MatchResult']