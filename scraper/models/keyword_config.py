"""Configuration for keyword matching in job descriptions."""
import hashlib
import json

# Bump when the matching/scoring logic changes (KeywordAnalyzer.analyze,
# MatchResult.calculate_score), so scores made by the old logic get a new
# scoring_version even with the same keywords.
SCORER_VERSION = 2  # 2: each keyword's count capped at MAX_SCORED_MATCHES

# Matches of one keyword that count toward weighted_score: presence matters,
# repetition (keyword-stuffed or very long postings) shouldn't.
MAX_SCORED_MATCHES = 2


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

    def scoring_version(self):
        """Short hash identifying how scores are computed with this config.

        Covers what changes a score: the keyword set, each keyword's weight,
        case sensitivity and SCORER_VERSION. Keyword order and weights for
        keywords not in the list don't affect scores, so they're left out.
        """
        canonical = json.dumps({
            'scorer': SCORER_VERSION,
            'case_sensitive': bool(self.case_sensitive),
            'weights': {kw: float(self.weights.get(kw, 1.0)) for kw in self.keywords},
        }, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:12]

    def keyword_score(self, keyword, count):
        """Weighted contribution of one keyword: weight x min(count, MAX_SCORED_MATCHES)."""
        return min(count, MAX_SCORED_MATCHES) * self.weights.get(keyword, 1.0)

    def get_keywords_string(self):
        """Get comma-separated keywords string for storage."""
        return ','.join(sorted(self.keywords))

    def __repr__(self):
        return f"KeywordConfig(keywords={self.keywords}, weights={self.weights})"
