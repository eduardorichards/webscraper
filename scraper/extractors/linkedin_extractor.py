"""LinkedIn-specific job extraction logic"""

from ..models.job import Job
from datetime import datetime


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
        
        
        posted_date, posted_time = self._extract_posted_datetime(card)
        if posted_date:
            job['posted_date'] = posted_date
        if posted_time:
            job['posted_time'] = posted_time
        
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
    
    def _extract_posted_datetime(self, card):
        """Extract posted date AND calculate actual time from 'ago' text"""
        time_element = card.find('time')
        
        if time_element:
            datetime_attr = time_element.get('datetime')
            
            if datetime_attr:
                try:
                    date_obj = datetime.fromisoformat(datetime_attr)
                    posted_date = date_obj.strftime('%Y-%m-%d')
                    
                    # Get the text to check if it's recent (within 24 hours)
                    time_text = time_element.get_text().strip().lower()
                    
                    # Calculate actual time if posted recently
                    posted_time = self._calculate_time_from_ago(time_text)
                    
                    return posted_date, posted_time
                except (ValueError, TypeError):
                    pass
            
            # Fallback to text
            text = time_element.get_text().strip()
            return text, 'Not specified'
        
        return 'Not specified', 'Not specified'

    def _calculate_time_from_ago(self, time_text):
        """Calculate actual posting time from 'X hours/minutes ago' text"""
        import re
        from datetime import timedelta
        
        now = datetime.now()
        
        # Check if it mentions hours or minutes (within 24 hours)
        if 'minuto' in time_text or 'minute' in time_text:
            # Extract number of minutes
            match = re.search(r'(\d+)\s*minuto', time_text)
            if match:
                minutes_ago = int(match.group(1))
                actual_time = now - timedelta(minutes=minutes_ago)
                return actual_time.strftime('%H:%M:%S')
        
        elif 'hora' in time_text or 'hour' in time_text:
            # Extract number of hours
            match = re.search(r'(\d+)\s*hora', time_text)
            if match:
                hours_ago = int(match.group(1))
                actual_time = now - timedelta(hours=hours_ago)
                return actual_time.strftime('%H:%M:%S')
        
        # If it's days, weeks, months - no specific time available
        return 'Not specified'
        
    def _extract_job_url(self, card):  
            """Extract job URL from job card"""

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