import requests
from bs4 import BeautifulSoup
from utils.helpers import clean_text
from utils.sqlite_storage import SQLiteStorage  # Updated import
import time

class Jobscraper:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0',
        }
        self.jobs = []
        self.sqlite_storage = SQLiteStorage()  # Use SQLite for storage
        
    def test_connection(self, url):
        """Test basic web scraping connection"""
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            print(f"✅ Connection successful to {url}")
            print(f"Page title: {soup.title.string if soup.title else 'No title found'}")
            
            return soup
        
        except Exception as e:
            print(f"❌ Error connecting to {url}: {e}")
            return None
        
    def extract_linkedin_jobs(self, soup):
        """Extract jobs using discovered LinkedIn structure - Focus on visible card info only"""
        
        print("\n🎯 EXTRACTING LINKEDIN JOBS")
        print("="*50)
        
        # Use the class we discovered: 'job-search-card'
        job_cards = soup.find_all('div', class_='job-search-card')
        
        print(f"Found {len(job_cards)} job cards")
        
        jobs_data = []
        
        for i, card in enumerate(job_cards[:15]):  # Changed back to 10 jobs
            # REMOVED: print(f"\n--- JOB {i+1} ---")  # Don't print during extraction
            
            job = {}
            
            # 1. Job Title/Position
            title_element = card.find('h3', class_='base-search-card__title')
            if title_element:
                job['title'] = title_element.get_text().strip()
            
            # 2. Company
            company_element = card.find('h4', class_='base-search-card__subtitle')
            if company_element:
                job['company'] = company_element.get_text().strip()
            
            # 3. Location and Work Modality - CLEAN FINAL VERSION
            all_text_elements = card.find_all(string=lambda text: 
                text and len(text.strip()) > 5
            )

            location_found = False

            # Look for text with work mode keywords in parentheses
            for text in all_text_elements:
                text_clean = text.strip()
                
                if '(' in text_clean and ')' in text_clean and len(text_clean) < 100:
                    parentheses_content = text_clean.split('(')[1].split(')')[0].strip().lower()
                    
                    work_mode_keywords = {
                        'remoto': 'Remote', 'remote': 'Remote', 
                        'híbrido': 'Hybrid', 'hibrido': 'Hybrid', 'hybrid': 'Hybrid',
                        'presencial': 'On-site', 'onsite': 'On-site', 'on-site': 'On-site',
                        'en remoto': 'Remote', 'en presencial': 'On-site'
                    }
                    
                    found_mode = None
                    for keyword, mode in work_mode_keywords.items():
                        if keyword in parentheses_content:
                            found_mode = mode
                            break
                    
                    if found_mode:
                        location_part = text_clean.split('(')[0].strip()
                        if ',' in location_part or any(indicator in location_part.lower() for indicator in ['ca', 'ny', 'tx', 'va', 'argentina']):
                            job['location'] = location_part
                            job['work_modality'] = found_mode
                            location_found = True
                            break

            # Look for regular location if no work mode found
            if not location_found:
                for text in all_text_elements:
                    text_clean = text.strip()
                    if len(text_clean) < 50 and (',' in text_clean or 'united states' in text_clean.lower()):
                        location_indicators = [', ca', ', ny', ', tx', ', va', ', fl', ', wa', 'united states']
                        if any(indicator in text_clean.lower() for indicator in location_indicators):
                            job['location'] = text_clean
                            job['work_modality'] = 'Not specified'
                            location_found = True
                            break

            # Check job title for remote indicators
            if not location_found or job.get('work_modality') == 'Not specified':
                title_text = job.get('title', '').lower()
                if any(remote_word in title_text for remote_word in ['remote', 'remoto']):
                    if not location_found:
                        job['location'] = 'Not specified'
                    job['work_modality'] = 'Remote'

            # Set defaults
            if 'location' not in job:
                job['location'] = 'Not specified'
            if 'work_modality' not in job:
                job['work_modality'] = 'Not specified'

            # 4. Publication Date
            time_element = card.find('time')
            if time_element:
                job['posted_date'] = time_element.get_text().strip()
            else:
                time_text = card.find(string=lambda text: text and any(
                    time_word in text.lower() for time_word in ['ago', 'day', 'hour', 'week', 'posted', 'hace']
                ))
                if time_text:
                    job['posted_date'] = time_text.strip()
            
            # 5. Job URL - Extract the link to the full job posting
            job_url = None

            # Look for the job link - it's usually in the title area
            title_link = card.find('a', class_='job-card-container__link')
            if title_link:
                href = title_link.get('href')
                if href:
                    # Convert relative URL to absolute URL
                    if href.startswith('/'):
                        job_url = f"https://www.linkedin.com{href}"
                    else:
                        job_url = href

            # Alternative: Look for any link containing '/jobs/view/'
            if not job_url:
                all_links = card.find_all('a')
                for link in all_links:
                    href = link.get('href', '')
                    if '/jobs/view/' in href:
                        if href.startswith('/'):
                            job_url = f"https://www.linkedin.com{href}"
                        else:
                            job_url = href
                        break

            # Store the job URL
            if job_url:
                job['job_url'] = job_url
            else:
                job['job_url'] = 'Not found'
            
            jobs_data.append(job)
        
        # Save jobs to SQLite database
        self.sqlite_storage.append_jobs(jobs_data, search_config=None)
        return jobs_data
    
    def build_linkedin_search_url(self, search_config):
        """Converts friendly params to LinkedIn query parameters"""
    
        base_url = "https://www.linkedin.com/jobs/search/"
        query_params = []
        
        # 1. Keywords
        if 'keywords' in search_config and search_config['keywords']:
            keywords = search_config['keywords'].strip()
            query_params.append(f"keywords={requests.utils.quote(keywords)}")
    
        # 2. Location
        if 'location' in search_config and search_config['location']:
            location = search_config['location'].strip()
            query_params.append(f"location={requests.utils.quote(location)}")
    
        # 3. Time Posted
        if 'time_posted' in search_config and search_config['time_posted']:
            time_posted = search_config['time_posted'].strip()
            time_mapping = {
                '24h': 'r86400',
                '1w': 'r604800',
                '1m': 'r2592000'
            }
            if time_posted in time_mapping:
                query_params.append(f"f_TPR={time_mapping[time_posted]}")
    
        # 4. Remote/On-site
        if 'remote' in search_config:
            remote = search_config['remote']
            if isinstance(remote, bool):
                if remote:
                    query_params.append("f_WT=2")  # Remote work
                # Note: LinkedIn doesn't have a specific "on-site only" filter
    
        # Combine base URL with query parameters
        if query_params:
            return f"{base_url}?{'&'.join(query_params)}"
        else:
            return base_url
    
if __name__ == "__main__":
    scraper = Jobscraper()
    
    # Define search configuration - SIMPLIFIED
    search_config = {
        'keywords': 'java',
        'location': 'España', 
        'time_posted': '24h',
        'remote': False
    }
    
    # Build URL using the new method
    search_url = scraper.build_linkedin_search_url(search_config)
    print(f"🔍 Generated Search URL: {search_url}")
    print()
    
    # Test connection with the generated URL
    soup = scraper.test_connection(search_url)    
    
    if soup:
        # Extract jobs focusing on visible card information
        jobs = scraper.extract_linkedin_jobs(soup)
        
        # Show summary
        print(f"\n📊 EXTRACTION RESULTS")
        print("="*50)
        print(f"Total jobs extracted: {len(jobs)}")
        print()
        
        for i, job in enumerate(jobs):
            print(f"--- JOB {i+1} ---")
            print(f"📋 Title: {job.get('title', 'N/A')}")
            print(f"🏢 Company: {job.get('company', 'N/A')}")
            print(f"📍 Location: {job.get('location', 'N/A')}")
            print(f"🏠 Work Mode: {job.get('work_modality', 'N/A')}")
            print(f"📅 Posted: {job.get('posted_date', 'N/A')}")
            print(f"🔗 URL: {job.get('job_url', 'N/A')}")
            print("-" * 30)
    else:
        print("❌ Failed to connect to LinkedIn")
