"""Base extractor class for job data extraction"""

from abc import ABC, abstractmethod
from ..models.job import Job


class BaseExtractor(ABC):
    """Abstract base class for job data extractors"""
    
    @abstractmethod
    def extract_jobs(self, soup, max_jobs=50):
        """
        Extract job data from HTML soup
        
        Args:
            soup: BeautifulSoup object containing the page HTML
            max_jobs (int): Maximum number of jobs to extract
            
        Returns:
            list[Job]: List of extracted job objects
        """
        pass
    
    @abstractmethod
    def extract_single_job(self, job_element):
        """
        Extract data from a single job element
        
        Args:
            job_element: BeautifulSoup element containing job data
            
        Returns:
            Job: Job object with extracted data
        """
        pass
    
    def _extract_text_safely(self, element, default="Not specified"):
        """Safely extract text from an element with fallback"""
        if element:
            text = element.get_text().strip()
            return text if text else default
        return default
    
    def _find_url_in_element(self, element, base_url=""):
        """Find and normalize URL from an element"""
        if not element:
            return "Not found"
        
        href = element.get('href', '')
        if not href:
            return "Not found"
        
        # Convert relative URL to absolute URL
        if href.startswith('/') and base_url:
            return f"{base_url}{href}"
        
        return href if href else "Not found"