"""Job data model"""


class Job:
    """Represents a job listing from a LinkedIn search result"""

    def __init__(self, title=None, company=None, location=None, company_url=None, linkedin_job_id=None, **kwargs):
        self.title = title or "Not specified"
        self.company = company or "Not specified"
        self.location = location or "Not specified"
        self.company_url = company_url
        self.linkedin_job_id = linkedin_job_id

    def to_dict(self):
        """Convert job to dictionary format"""
        return {
            'title': self.title,
            'company': self.company,
            'location': self.location,
            'company_url': self.company_url,
            'linkedin_job_id': self.linkedin_job_id
        }

    def __str__(self):
        return f"Job(title='{self.title}', company='{self.company}', location='{self.location}')"

    def __repr__(self):
        return self.__str__()
