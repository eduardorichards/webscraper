"""Orchestrator for keyword matching workflow."""
from ..models.match_result import MatchResult
from ..analyzers.keyword_analyzer import KeywordAnalyzer
from .detail_scraper import DetailScraper


class KeywordMatcher:
    """Orchestrates the keyword matching workflow."""

    def __init__(self, sqlite_storage, keyword_config):
        """
        Initialize the keyword matcher.

        Args:
            sqlite_storage: SQLiteStorage instance
            keyword_config: KeywordConfig instance with keywords to match
        """
        self.storage = sqlite_storage
        self.keyword_config = keyword_config
        self.detail_scraper = DetailScraper()
        self.analyzer = KeywordAnalyzer(keyword_config)

    def analyze_jobs(self, job_ids=None, skip_analyzed=True):
        """
        Analyze jobs for keyword matches.

        Args:
            job_ids: Specific job IDs to analyze, or None for all unanalyzed
            skip_analyzed: Skip jobs that already have analysis (default True)

        Returns:
            list[MatchResult]: Results sorted by weighted_score descending
        """
        # Get jobs to analyze
        search_keywords = self.keyword_config.get_keywords_string()

        if job_ids:
            jobs = self.storage.get_jobs_by_ids(job_ids)
        elif skip_analyzed:
            jobs = self.storage.get_jobs_without_analysis(search_keywords)
        else:
            jobs = self.storage.get_all_jobs()

        if not jobs:
            print("No jobs to analyze.")
            return []

        print(f"\n📊 Analyzing {len(jobs)} jobs for {len(self.keyword_config.keywords)} keywords...")
        print(f"   Keywords: {', '.join(self.keyword_config.keywords[:5])}{'...' if len(self.keyword_config.keywords) > 5 else ''}")

        results = []

        for i, job in enumerate(jobs):
            job_id = job['id']
            job_url = job['job_url']

            print(f"\n  [{i + 1}/{len(jobs)}] {job.get('title', 'Unknown')[:50]}...")

            # Create result object
            result = MatchResult(
                job_id=job_id,
                job_url=job_url,
                title=job.get('title'),
                company=job.get('company')
            )

            # Scrape job details
            details = self.detail_scraper.scrape_job_details(job_url)

            if details:
                result.description = details.get('description')
                result.applicant_count = details.get('applicant_count')
                result.seniority_level = details.get('seniority_level')
                result.employment_type = details.get('employment_type')
                result.job_function = details.get('job_function')
                result.industries = details.get('industries')
                result.scrape_status = 'success'

                # Analyze for keywords
                result.keyword_matches = self.analyzer.analyze(result.description)
                result.calculate_score(self.keyword_config)

                print(f"      ✓ Score: {result.weighted_score:.1f} | Match: {result.match_percentage:.0f}% | Applicants: {result.applicant_count or 'N/A'}")
            else:
                result.scrape_status = 'failed'
                result.keyword_matches = {kw: 0 for kw in self.keyword_config.keywords}
                print(f"      ✗ Failed to scrape")

            # Save to database immediately (for resume capability)
            self.storage.save_job_analysis(result, self.keyword_config)
            results.append(result)

        # Sort by score descending
        results.sort(key=lambda r: r.weighted_score, reverse=True)

        print(f"\n✅ Analysis complete! {len(results)} jobs analyzed.")

        return results

    def get_ranked_jobs(self, min_score=0, min_keywords=0, limit=None):
        """
        Get previously analyzed jobs, ranked by score.

        Args:
            min_score: Minimum weighted score threshold
            min_keywords: Minimum number of matched keywords
            limit: Maximum number of results

        Returns:
            list[dict]: Jobs with analysis, sorted by score
        """
        search_keywords = self.keyword_config.get_keywords_string()
        return self.storage.get_analyzed_jobs(
            search_keywords=search_keywords,
            min_score=min_score,
            min_keywords=min_keywords,
            limit=limit
        )

    def display_results(self, results, top_n=10):
        """
        Display analysis results in a formatted way.

        Args:
            results: List of MatchResult objects or dicts from get_ranked_jobs
            top_n: Number of top results to display
        """
        print(f"\n{'=' * 70}")
        print(f"TOP {min(top_n, len(results))} JOBS BY KEYWORD MATCH SCORE")
        print('=' * 70)

        for i, result in enumerate(results[:top_n], 1):
            # Handle both MatchResult objects and dicts
            if isinstance(result, MatchResult):
                score = result.weighted_score
                match_pct = result.match_percentage
                applicants = result.applicant_count
                matched_kws = result.matched_keywords
                title = result.title
                company = result.company
                url = result.job_url
            else:
                score = result.get('weighted_score', 0)
                match_pct = result.get('match_percentage', 0)
                applicants = result.get('applicant_count')
                matched_kws = result.get('matched_keywords', [])
                title = result.get('title', 'Unknown')
                company = result.get('company', 'Unknown')
                url = result.get('job_url', '')

            print(f"\n{i}. {title}")
            print(f"   Company: {company}")
            print(f"   Score: {score:.1f} | Match: {match_pct:.0f}% | Applicants: {applicants or 'N/A'}")
            print(f"   Keywords: {', '.join(matched_kws) if matched_kws else 'None'}")
            print(f"   URL: {url}")

        print(f"\n{'=' * 70}")
