"""Keyword analyzer for matching keywords in job descriptions."""
import re


class KeywordAnalyzer:
    """Analyzes job descriptions for keyword matches."""

    def __init__(self, keyword_config):
        """
        Initialize the analyzer.

        Args:
            keyword_config: KeywordConfig instance with keywords and settings
        """
        self.keyword_config = keyword_config

    def analyze(self, description):
        """
        Analyze a job description for keyword matches.

        Args:
            description: Full job description text

        Returns:
            dict: {keyword: match_count}
        """
        if not description:
            return {kw: 0 for kw in self.keyword_config.keywords}

        # Prepare text based on case sensitivity setting
        text = description if self.keyword_config.case_sensitive else description.lower()

        matches = {}
        for keyword in self.keyword_config.keywords:
            search_kw = keyword if self.keyword_config.case_sensitive else keyword.lower()

            # Use word boundary matching for accurate counts
            # Handles phrases like "REST API" and single words like "Python"
            # Escape special regex characters in the keyword
            pattern = r'\b' + re.escape(search_kw) + r'\b'

            flags = 0 if self.keyword_config.case_sensitive else re.IGNORECASE
            count = len(re.findall(pattern, text, flags))
            matches[keyword] = count

        return matches

    def analyze_batch(self, descriptions):
        """
        Analyze multiple job descriptions.

        Args:
            descriptions: dict {job_id: description}

        Returns:
            dict: {job_id: {keyword: count}}
        """
        return {
            job_id: self.analyze(desc)
            for job_id, desc in descriptions.items()
        }

    def get_summary(self, keyword_matches):
        """
        Get a summary of keyword matches.

        Args:
            keyword_matches: dict {keyword: count}

        Returns:
            dict with summary statistics
        """
        total_matches = sum(keyword_matches.values())
        matched_keywords = [k for k, v in keyword_matches.items() if v > 0]
        match_percentage = (
            len(matched_keywords) / len(self.keyword_config.keywords) * 100
            if self.keyword_config.keywords else 0
        )

        # Calculate weighted score
        weighted_score = sum(
            count * self.keyword_config.weights.get(kw, 1.0)
            for kw, count in keyword_matches.items()
        )

        return {
            'total_matches': total_matches,
            'matched_keywords': matched_keywords,
            'match_percentage': match_percentage,
            'weighted_score': weighted_score,
        }
