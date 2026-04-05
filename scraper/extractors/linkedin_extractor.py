"""LinkedIn-specific job extraction logic"""

from ..models.job import Job
from urllib.parse import urlparse, urlunparse
import re


class LinkedInExtractor:
    """Extract job data from LinkedIn pages"""

    def extract_jobs(self, soup, max_results=10):
        """Extract jobs from LinkedIn search results"""
        print(f"\n🎯 EXTRACTING LINKEDIN JOBS")
        print("="*50)

        # Find job cards
        job_cards = soup.find_all('div', class_='job-search-card')
        print(f"Found {len(job_cards)} job cards")

        jobs = []

        for i, card in enumerate(job_cards[:max_results]):
            job_data = self._extract_single_job(card)
            if job_data:
                jobs.append(Job(**job_data))

        return jobs

    def _extract_single_job(self, card):
        job = {}

        # Title
        title_element = card.find('h3', class_='base-search-card__title')
        if title_element:
            job['title'] = title_element.get_text().strip()

        # Company
        company_element = card.find('h4', class_='base-search-card__subtitle')
        if company_element:
            job['company'] = company_element.get_text().strip()
            company_url = self._extract_company_url(company_element)
            if company_url:
                job['company_url'] = company_url

        location = self._extract_location(card)
        job['location'] = location

        # LinkedIn Job ID
        linkedin_job_id = self._extract_linkedin_job_id(card)
        if linkedin_job_id:
            job['linkedin_job_id'] = linkedin_job_id

        return job

    def _extract_location(self, card):
        location_element = card.find('span', class_='job-search-card__location')

        if location_element:
            location_text = location_element.get_text().strip()
            return location_text
        else:
            return 'Not found'

    def _extract_company_url(self, company_element):
        """Extract company LinkedIn profile URL from the company name link."""
        link = company_element.find('a')
        if not link:
            return None
        href = link.get('href')
        if not href or '/company/' not in href:
            return None
        # Normalize domain and strip tracking query params
        parsed = urlparse(href)
        clean_url = urlunparse((
            parsed.scheme or 'https',
            'www.linkedin.com',
            parsed.path,
            '', '', ''
        ))
        return clean_url

    def _extract_linkedin_job_id(self, card):
        """Extract LinkedIn job ID from job card.

        Returns:
            str: LinkedIn job ID or None
        """
        title_link = card.find('a', class_='job-card-container__link')
        if title_link:
            href = title_link.get('href')
            if href:
                job_id = self._extract_id_from_url(href)
                if job_id:
                    return job_id

        # Fallback: Look for any link containing '/jobs/view/'
        all_links = card.find_all('a')
        for link in all_links:
            href = link.get('href', '')
            if '/jobs/view/' in href:
                job_id = self._extract_id_from_url(href)
                if job_id:
                    return job_id

        return None

    def _extract_id_from_url(self, href):
        """Extract job ID from a LinkedIn URL.

        Returns:
            str: job ID or None
        """
        match = re.search(r'/jobs/view/[^/]*?(\d{5,})', href)
        if match:
            return match.group(1)
        return None
