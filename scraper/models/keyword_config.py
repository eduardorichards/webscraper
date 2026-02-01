"""Configuration for keyword matching in job descriptions."""


class KeywordConfig:
    """Stores user-defined keywords and optional weights for matching."""

    def __init__(self, keywords, weights=None, case_sensitive=False):
        """
        Initialize keyword configuration.

        Args:
            keywords: List of keywords to match (e.g., ["Python", "Django", "REST API"])
            weights: Optional dict mapping keywords to weights (default: 1.0 each)
            case_sensitive: Whether matching is case-sensitive (default: False)
        """
        self.keywords = keywords
        self.weights = weights or {kw: 1.0 for kw in keywords}
        self.case_sensitive = case_sensitive

        # Ensure all keywords have weights
        for kw in self.keywords:
            if kw not in self.weights:
                self.weights[kw] = 1.0

    def to_dict(self):
        """Convert config to dictionary."""
        return {
            'keywords': self.keywords,
            'weights': self.weights,
            'case_sensitive': self.case_sensitive
        }

    def get_keywords_string(self):
        """Get comma-separated keywords string for storage."""
        return ','.join(sorted(self.keywords))

    def __repr__(self):
        return f"KeywordConfig(keywords={self.keywords}, weights={self.weights})"
