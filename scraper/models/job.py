"""Job data model"""

class Job:
    """Represents a job listing with all extracted information"""
    
    def __init__(self, title=None, company=None, location=None, 
                 work_modality=None, posted_date=None, job_url=None, **kwargs):
        self.title = title or "Not specified"
        self.company = company or "Not specified"
        self.location = location or "Not specified"
        self.work_modality = work_modality or "Not specified"
        self.posted_date = posted_date or "Not specified"
        self.job_url = job_url or "Not found"
        
        # Store any additional fields
        for key, value in kwargs.items():
            setattr(self, key, value)
    
    def to_dict(self):
        """Convert job to dictionary format"""
        return {
            'title': self.title,
            'company': self.company,
            'location': self.location,
            'work_modality': self.work_modality,
            'posted_date': self.posted_date,
            'job_url': self.job_url
        }
    
    def __str__(self):
        return f"Job(title='{self.title}', company='{self.company}', location='{self.location}')"
    
    def __repr__(self):
        return self.__str__()