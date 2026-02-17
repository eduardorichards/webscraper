"""Model for storing keyword match results for a job."""


class MatchResult:
    """Stores keyword match analysis results for a single job."""

    def __init__(self, job_id, job_url, title=None, company=None):
        """
        Initialize match result.

        Args:
            job_id: Database ID of the job
            job_url: URL of the job posting
            title: Job title (optional, for display)
            company: Company name (optional, for display)
        """
        self.job_id = job_id
        self.job_url = job_url
        self.title = title
        self.company = company

        # Scraped data
        self.description = None
        self.applicant_count = None
        self.employment_type = None
        self.job_function = None

        # Match results
        self.keyword_matches = {}  # {keyword: count}
        self.total_matches = 0
        self.weighted_score = 0.0
        self.matched_keywords = []  # Keywords found at least once
        self.match_percentage = 0.0

        # Status
        self.scrape_status = 'pending'  # 'pending', 'success', 'failed'

    def calculate_score(self, keyword_config):
        """
        Calculate weighted score based on matches and weights.

        Args:
            keyword_config: KeywordConfig instance with weights
        """
        self.total_matches = sum(self.keyword_matches.values())
        self.matched_keywords = [k for k, v in self.keyword_matches.items() if v > 0]

        if keyword_config.keywords:
            self.match_percentage = (
                len(self.matched_keywords) / len(keyword_config.keywords) * 100
            )
        else:
            self.match_percentage = 0.0

        # Weighted score: sum of (count * weight) for each keyword
        self.weighted_score = sum(
            count * keyword_config.weights.get(kw, 1.0)
            for kw, count in self.keyword_matches.items()
        )

    def to_dict(self):
        """Convert result to dictionary for storage."""
        return {
            'job_id': self.job_id,
            'job_url': self.job_url,
            'title': self.title,
            'company': self.company,
            'description': self.description,
            'applicant_count': self.applicant_count,
            'employment_type': self.employment_type,
            'job_function': self.job_function,
            'total_matches': self.total_matches,
            'weighted_score': self.weighted_score,
            'matched_keywords': self.matched_keywords,
            'match_percentage': self.match_percentage,
            'scrape_status': self.scrape_status,
        }

    def __repr__(self):
        return (
            f"MatchResult(job_id={self.job_id}, score={self.weighted_score:.1f}, "
            f"match={self.match_percentage:.0f}%)"
        )
