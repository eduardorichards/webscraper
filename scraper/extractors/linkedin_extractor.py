"""LinkedIn-specific job extraction logic"""

from ..models.job import Job


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
        
        location = self._extract_location(card)
        job['location'] = location
        
        
        posted_date = self._extract_posted_date(card)
        if posted_date:
            job['posted_date'] = posted_date
        
        # Job URL
        job_url = self._extract_job_url(card)
        if job_url:
            job['job_url'] = job_url
        
        return job
    
    def _extract_location(self, card):
        
        location_element = card.find('span', class_='job-search-card__location')
        
        if location_element:
            location_text = location_element.get_text().strip()
            return location_text
        else:
            return 'Not found'
    
    def _extract_posted_date(self, card):
        """Extract posted date from job card"""
        time_element = card.find('time')
        if time_element:
            return time_element.get_text().strip()
        
        # Alternative: look for text with time keywords
        time_text = card.find(string=lambda text: text and any(
            time_word in text.lower() for time_word in ['ago', 'day', 'hour', 'week', 'posted', 'hace']
        ))
        if time_text:
            return time_text.strip()
        
        return 'Not specified'
    
    def _extract_job_url(self, card):
        """Extract job URL from job card"""
        # Look for job link
        title_link = card.find('a', class_='job-card-container__link')
        if title_link:
            href = title_link.get('href')
            if href:
                if href.startswith('/'):
                    # Force www.linkedin.com instead of country-specific domain
                    return f"https://www.linkedin.com{href}"
                else:
                    # Replace country-specific domain with global
                    if 'ar.linkedin.com' in href:
                        return href.replace('ar.linkedin.com', 'www.linkedin.com')
                    return href
        
        # Alternative: Look for any link containing '/jobs/view/'
        all_links = card.find_all('a')
        for link in all_links:
            href = link.get('href', '')
            if '/jobs/view/' in href:
                if href.startswith('/'):
                    return f"https://www.linkedin.com{href}"
                else:
                    # Replace country-specific domain
                    if 'ar.linkedin.com' in href:
                        return href.replace('ar.linkedin.com', 'www.linkedin.com')
                    return href
        
        return 'Not found'