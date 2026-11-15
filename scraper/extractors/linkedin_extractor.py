"""LinkedIn-specific job extraction logic"""

from ..models.job import Job
from urllib.parse import urlparse, urlunparse
import logging
import re

logger = logging.getLogger(__name__)

# LinkedIn job IDs are 10 digits (~4.4 billion in Nov 2026, growing ~13M/month)
VALID_JOB_ID = re.compile(r'[0-9]{10}')
_URN_ID = re.compile(r'^urn:li:jobPosting:(\d+)$')
# Last digit run of the /jobs/view/ path segment: "/jobs/view/<slug>-<id>" or
# "/jobs/view/<id>". Slugs can contain numbers from the title, so never take
# the first one.
_URL_ID = re.compile(r'/jobs/view/(?:[^/?#]*?-)?(\d+)/?(?:[?#]|$)')


def is_valid_job_id(job_id):
    """True if job_id looks like a real LinkedIn job ID (exactly 10 digits)."""
    return bool(job_id) and bool(VALID_JOB_ID.fullmatch(job_id))


class LinkedInExtractor:
    """Extract job data from LinkedIn pages"""

    def __init__(self):
        self.last_card_count = 0  # Cards on the page passed to the last extract_jobs()

    def extract_jobs(self, soup, max_results=10):
        """Extract jobs from LinkedIn search results.

        Cards without a valid job ID are skipped and logged. The number of
        cards on the page (valid or not) is kept in self.last_card_count.
        """
        print(f"\n🎯 EXTRACTING LINKEDIN JOBS")
        print("="*50)

        # Find job cards
        job_cards = soup.find_all('div', class_='job-search-card')
        self.last_card_count = len(job_cards)
        print(f"Found {len(job_cards)} job cards")

        jobs = []

        for i, card in enumerate(job_cards[:max_results]):
            job_data = self._extract_single_job(card)
            if not is_valid_job_id(job_data.get('linkedin_job_id')):
                logger.warning(
                    "Skipping job card without a valid 10-digit job ID: "
                    "id=%r title=%r href=%r",
                    job_data.get('linkedin_job_id'), job_data.get('title'),
                    self._job_href(card))
                continue
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
        """Extract the LinkedIn job ID from a job card.

        Uses the card's data-entity-urn ("urn:li:jobPosting:<id>"), falling
        back to the /jobs/view/ link. Never parsed from the title.

        Returns:
            str: job ID (not yet validated) or None
        """
        match = _URN_ID.match(card.get('data-entity-urn') or '')
        if match:
            return match.group(1)

        href = self._job_href(card)
        if href:
            return self._extract_id_from_url(href)
        return None

    @staticmethod
    def _job_href(card):
        """href of the card's first /jobs/view/ link, or None."""
        for link in card.find_all('a', href=True):
            if '/jobs/view/' in link['href']:
                return link['href']
        return None

    def _extract_id_from_url(self, href):
        """Extract the job ID from a LinkedIn job URL (the path's last number).

        Returns:
            str: job ID or None
        """
        match = _URL_ID.search(href)
        if match:
            return match.group(1)
        return None
