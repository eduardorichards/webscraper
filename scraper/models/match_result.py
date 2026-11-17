"""Model for storing keyword match results for a job."""

from datetime import datetime, timezone

from utils.job_keys import LINKEDIN_JOB_BASE_URL, job_url_for  # noqa: F401


class MatchResult:
    """Stores keyword match analysis results for a single job post."""

    def __init__(self, linkedin_job_id, source_url=None):
        self.linkedin_job_id = linkedin_job_id
        # Posting URL stored for non-LinkedIn jobs (job_searches.job_url)
        self.source_url = source_url

        # Scraped data
        self.description = None
        self.applicant_count = None
        # 'under' / 'over' when LinkedIn shows a bound, None for an exact count
        self.applicant_count_qualifier = None
        self.employment_type = None
        self.job_function = None
        self.seniority_level = None
        self.industries = None
        self.date_time = None  # Timestamp when analysis started (set even if the fetch fails)
        self.scraped_at = None  # Timestamp when details were fetched (None if the fetch failed)
        self.apply_type = None  # 'easy_apply' / 'external', None if unknown
        self.apply_url = None  # External apply URL, when the page exposes it
        self.posted_at = None  # Posting date given by the source (ATS jobs only)

        # Match results
        self.keyword_matches = {}  # {keyword: count}
        self.total_matches = 0
        self.weighted_score = 0.0
        self.matched_keywords = []  # Keywords found at least once
        self.match_percentage = 0.0
        # KeywordConfig.scoring_version() of the score; None if nothing was scored
        self.scoring_version = None

    @property
    def job_url(self):
        """LinkedIn URL built from the ID, or the stored URL of other sources."""
        return job_url_for(self.linkedin_job_id, self.source_url)

    def calculate_score(self, keyword_config):
        """Calculate weighted score based on matches and weights."""
        self.total_matches = sum(self.keyword_matches.values())
        self.matched_keywords = [k for k, v in self.keyword_matches.items() if v > 0]

        if keyword_config.keywords:
            self.match_percentage = (
                len(self.matched_keywords) / len(keyword_config.keywords) * 100
            )
        else:
            self.match_percentage = 0.0

        self.weighted_score = sum(
            keyword_config.keyword_score(kw, count)
            for kw, count in self.keyword_matches.items()
        )
        self.scoring_version = keyword_config.scoring_version()

    def to_dict(self):
        """Convert result to dictionary for storage."""
        return {
            'linkedin_job_id': self.linkedin_job_id,
            'description': self.description,
            'applicant_count': self.applicant_count,
            'applicant_count_qualifier': self.applicant_count_qualifier,
            'date_time': self.date_time,
            'scraped_at': self.scraped_at,
            'apply_type': self.apply_type,
            'apply_url': self.apply_url,
            'total_matches': self.total_matches,
            'weighted_score': self.weighted_score,
            'matched_keywords': self.matched_keywords,
            'match_percentage': self.match_percentage,
            'employment_type': self.employment_type,
            'job_function': self.job_function,
            'seniority_level': self.seniority_level,
            'industries': self.industries,
            'scoring_version': self.scoring_version,
            'posted_at': self.posted_at,
        }

    def __repr__(self):
        return (
            f"MatchResult(linkedin_job_id={self.linkedin_job_id}, "
            f"score={self.weighted_score:.1f}, match={self.match_percentage:.0f}%)"
        )
