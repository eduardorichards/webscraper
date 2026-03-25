"""Job data model"""

class Job:
    """Represents a job listing with all extracted information"""
    
    def __init__(self, title=None, company=None, location=None, posted_date=None, job_url=None, company_url=None, **kwargs):
        self.title = title or "Not specified"
        self.company = company or "Not specified"
        self.location = location or "Not specified"
        self.posted_date = posted_date or "Not specified"
        self.job_url = job_url or "Not found"
        self.company_url = company_url
        
        # Store any additional fields
        for key, value in kwargs.items():
            setattr(self, key, value)
    
    def to_dict(self):
        """Convert job to dictionary format"""
        return {
            'title': self.title,
            'company': self.company,
            'location': self.location,
            'posted_date': self.posted_date,
            'job_url': self.job_url,
            'company_url': self.company_url
        }
    
    def __str__(self):
        return f"Job(title='{self.title}', company='{self.company}', location='{self.location}')"
    
    def __repr__(self):
        return self.__str__()