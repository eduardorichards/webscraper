"""Search configuration model"""

class SearchConfig:
    """Represents search parameters for job scraping"""
    
    def __init__(self, keywords=None, location=None, time_posted=None, remote=None, 
                 experience_levels=None, max_results=50):
        self.keywords = keywords or ""
        self.location = location or ""
        self.time_posted = time_posted or "1w"  # Default to 1 week
        self.remote = remote if remote is not None else False
        self.experience_levels = experience_levels or []  # List of integers 1-6
        self.max_results = max_results
    
    def __str__(self):
        return f"SearchConfig(keywords='{self.keywords}', location='{self.location}', experience_levels={self.experience_levels}, remote={self.remote})"
    
    def to_dict(self):
        """Convert search config to dictionary format"""
        return {
            'keywords': self.keywords,
            'location': self.location,
            'time_posted': self.time_posted,
            'remote': self.remote,
            'experience_levels': self.experience_levels,
            'max_results': self.max_results
        }
    
    def is_valid(self):
        """Check if the search configuration is valid"""
        # Check experience levels are valid (1-6)
        if self.experience_levels:
            for level in self.experience_levels:
                if not isinstance(level, int) or level < 1 or level > 6:
                    return False, f"Experience level {level} must be integer between 1-6"
        
        # Check max_results is positive
        if self.max_results <= 0:
            return False, "max_results must be positive"
            
        # At least keywords or location should be specified
        return bool(self.keywords.strip() or self.location.strip()), "Valid configuration"