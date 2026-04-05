"""Model for storing keyword match results for a job."""

from datetime import datetime, timezone

LINKEDIN_JOB_BASE_URL = "https://www.linkedin.com/jobs/view/"


class MatchResult:
    """Stores keyword match analysis results for a single job post."""

    def __init__(self, linkedin_job_id):
        self.linkedin_job_id = linkedin_job_id

        # Scraped data
        self.description = None
        self.applicant_count = None
        self.employment_type = None
        self.job_function = None
        self.seniority_level = None
        self.industries = None
        self.date_time = None  # Timestamp when the job page was scraped

        # Match results
        self.keyword_matches = {}  # {keyword: count}
        self.total_matches = 0
        self.weighted_score = 0.0
        self.matched_keywords = []  # Keywords found at least once
        self.match_percentage = 0.0

    @property
    def job_url(self):
        """Construct job URL from linkedin_job_id."""
        return f"{LINKEDIN_JOB_BASE_URL}{self.linkedin_job_id}/"

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
            count * keyword_config.weights.get(kw, 1.0)
            for kw, count in self.keyword_matches.items()
        )

    def to_dict(self):
        """Convert result to dictionary for storage."""
        return {
            'linkedin_job_id': self.linkedin_job_id,
            'description': self.description,
            'applicant_count': self.applicant_count,
            'date_time': self.date_time,
            'total_matches': self.total_matches,
            'weighted_score': self.weighted_score,
            'matched_keywords': self.matched_keywords,
            'match_percentage': self.match_percentage,
            'employment_type': self.employment_type,
            'job_function': self.job_function,
            'seniority_level': self.seniority_level,
            'industries': self.industries,
        }

    def __repr__(self):
        return (
            f"MatchResult(linkedin_job_id={self.linkedin_job_id}, "
            f"score={self.weighted_score:.1f}, match={self.match_percentage:.0f}%)"
        )
