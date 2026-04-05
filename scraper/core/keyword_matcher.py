"""Orchestrator for keyword matching workflow."""
from datetime import datetime, timezone

from ..models.match_result import MatchResult, LINKEDIN_JOB_BASE_URL
from ..analyzers.keyword_analyzer import KeywordAnalyzer
from .detail_scraper import DetailScraper


class KeywordMatcher:
    """Orchestrates the keyword matching workflow."""

    def __init__(self, sqlite_storage, keyword_config):
        self.storage = sqlite_storage
        self.keyword_config = keyword_config
        self.detail_scraper = DetailScraper()
        self.analyzer = KeywordAnalyzer(keyword_config)

    def analyze_jobs(self, skip_analyzed=True):
        """
        Analyze jobs for keyword matches.

        Args:
            skip_analyzed: Skip jobs that already have analysis (default True)

        Returns:
            list[MatchResult]: Results sorted by weighted_score descending
        """
        if skip_analyzed:
            jobs = self.storage.get_jobs_without_analysis()
        else:
            jobs = self.storage.get_jobs_without_analysis()

        if not jobs:
            print("No jobs to analyze.")
            return []

        print(f"\n📊 Analyzing {len(jobs)} jobs for {len(self.keyword_config.keywords)} keywords...")
        print(f"   Keywords: {', '.join(self.keyword_config.keywords[:5])}{'...' if len(self.keyword_config.keywords) > 5 else ''}")

        results = []

        for i, job in enumerate(jobs):
            linkedin_job_id = job['linkedin_job_id']
            job_url = f"{LINKEDIN_JOB_BASE_URL}{linkedin_job_id}/"

            print(f"\n  [{i + 1}/{len(jobs)}] {job.get('title', 'Unknown')[:50]}...")

            result = MatchResult(linkedin_job_id=linkedin_job_id)
            result.date_time = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

            # Scrape job details
            details = self.detail_scraper.scrape_job_details(job_url)

            if details:
                result.description = details.get('description')
                result.applicant_count = details.get('applicant_count')
                result.employment_type = details.get('employment_type')
                result.job_function = details.get('job_function')
                result.seniority_level = details.get('seniority_level')
                result.industries = details.get('industries')

                # Analyze for keywords
                result.keyword_matches = self.analyzer.analyze(result.description)
                result.calculate_score(self.keyword_config)

                print(f"      ✓ Score: {result.weighted_score:.1f} | Match: {result.match_percentage:.0f}% | Applicants: {result.applicant_count or 'N/A'}")
            else:
                result.keyword_matches = {kw: 0 for kw in self.keyword_config.keywords}
                print(f"      ✗ Failed to scrape")

            # Save to database immediately (for resume capability)
            self.storage.save_job_analysis(result)
            results.append(result)

        # Sort by score descending
        results.sort(key=lambda r: r.weighted_score, reverse=True)

        print(f"\n✅ Analysis complete! {len(results)} jobs analyzed.")

        return results

    def get_ranked_jobs(self, min_score=0, min_keywords=0, limit=None):
        """Get previously analyzed jobs, ranked by score."""
        return self.storage.get_analyzed_jobs(
            min_score=min_score,
            min_keywords=min_keywords,
            limit=limit
        )

    def display_results(self, results, top_n=10):
        """Display analysis results in a formatted way."""
        print(f"\n{'=' * 70}")
        print(f"TOP {min(top_n, len(results))} JOBS BY KEYWORD MATCH SCORE")
        print('=' * 70)

        for i, result in enumerate(results[:top_n], 1):
            if isinstance(result, MatchResult):
                score = result.weighted_score
                match_pct = result.match_percentage
                applicants = result.applicant_count
                matched_kws = result.matched_keywords
                url = result.job_url
                linkedin_id = result.linkedin_job_id
            else:
                score = result.get('weighted_score', 0)
                match_pct = result.get('match_percentage', 0)
                applicants = result.get('applicant_count')
                matched_kws = result.get('matched_keywords', [])
                linkedin_id = result.get('linkedin_job_id', '')
                url = f"{LINKEDIN_JOB_BASE_URL}{linkedin_id}/"

            title = result.get('title', 'Unknown') if isinstance(result, dict) else linkedin_id
            company = result.get('company', 'Unknown') if isinstance(result, dict) else ''

            print(f"\n{i}. {title}")
            print(f"   Company: {company}")
            print(f"   Score: {score:.1f} | Match: {match_pct:.0f}% | Applicants: {applicants or 'N/A'}")
            print(f"   Keywords: {', '.join(matched_kws) if matched_kws else 'None'}")
            print(f"   URL: {url}")

        print(f"\n{'=' * 70}")
