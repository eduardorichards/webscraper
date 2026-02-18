"""Application settings and configuration"""

# LinkedIn scraping settings
LINKEDIN_BASE_URL = "https://www.linkedin.com/jobs/search/"

# Request headers for better LinkedIn compatibility
DEFAULT_HEADERS = {
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

# Time posted mapping for LinkedIn
TIME_POSTED_MAPPING = {
    '1h': '3600',
    '2h': '7200',
    '24': '86400',
    '1w': '604800',
    '1m': '2592000'
}

# Experience level mapping
EXPERIENCE_LEVELS = {
    1: "Internship",
    2: "Entry level", 
    3: "Associate",
    4: "Mid-Senior level",
    5: "Director",
    6: "Executive"
}

# Valid experience level range
MIN_EXPERIENCE_LEVEL = 1
MAX_EXPERIENCE_LEVEL = 6

# Work mode keywords (English and Spanish)
WORK_MODE_KEYWORDS = {
    'remoto': 'Remote',
    'remote': 'Remote', 
    'híbrido': 'Hybrid',
    'hibrido': 'Hybrid',  # Without accent
    'hybrid': 'Hybrid',
    'presencial': 'On-site',
    'onsite': 'On-site',
    'on-site': 'On-site',
    'en remoto': 'Remote',
    'presencial': 'On-site'
}

# Location indicators for validation
LOCATION_INDICATORS = [
    ', ca', ', ny', ', tx', ', va', ', fl', ', wa', 
    'united states', 'argentina', 'méxico', 'chile'
]

# Default extraction limits
DEFAULT_MAX_JOBS = 50
DEFAULT_PROCESSING_LIMIT = 100


SEARCH_TEMPLATES = [
        {
        "name": "Developer Arg Jr",
        "keywords": "Junior Developer",
        "location": "Argentina",
        "experience_levels": [1, 2],
        "remote": False,
        "time_posted": "1h",
        "max_results": 100
    },
    {
        "name": "Java Arg Jr",
        "keywords": "Java",
        "location": "Argentina",
        "experience_levels": [1, 2],
        "remote": False,
        "time_posted": "1h",
        "max_results": 100
    },
    {
        "name": "Python Arg Jr",
        "keywords": "Python",
        "location": "Argentina",
        "experience_levels": [1, 2],
        "remote": False,
        "time_posted": "1h",
        "max_results": 100
    },    
    {
        "name": "Backend Arg Jr Remote",
        "keywords": "Backend",
        "location": "Argentina",
        "experience_levels": [1, 2],
        "remote": False,
        "time_posted": "1h",
        "max_results": 100
    },
    {
        "name": "Software Developer Arg Jr Remote",
        "keywords": "Software Developer",
        "location": "Argentina",
        "experience_levels": [1, 2],
        "remote": False,
        "time_posted": "1h",
        "max_results": 100
    },
    {
        "name": "Fullstack Arg Jr Remote",
        "keywords": "Fullstack",
        "location": "Argentina",
        "experience_levels": [1, 2],
        "remote": False,
        "time_posted": "1h",
        "max_results": 100
    },
    {
        "name": "Java Latam Remote",
        "keywords": "Java",
        "location": "Latin America",
        "experience_levels": [1, 2],
        "remote": True,
        "time_posted": "1h",
        "max_results": 100
    },
    {
        "name": "Python Latam Remote",
        "keywords": "Python",
        "location": "Latin America",
        "experience_levels": [1, 2],
        "remote": True,
        "time_posted": "1h",
        "max_results": 100
    },    
    {
        "name": "Backend Latam Remote",
        "keywords": "Backend",
        "location": "Latin America",
        "experience_levels": [1, 2],
        "remote": True,
        "time_posted": "1h",
        "max_results": 100
    },
    {
        "name": "Software Developer Latam Remote",
        "keywords": "Software Developer",
        "location": "Latin America",
        "experience_levels": [1, 2],
        "remote": True,
        "time_posted": "1h",
        "max_results": 100
    },
    {
        "name": "Fullstack Latam Remote",
        "keywords": "Fullstack",
        "location": "Latin America",
        "experience_levels": [1, 2],
        "remote": True,
        "time_posted": "1h",
        "max_results": 100
    },
    {
        "name": "Developer Jr Latam Remote",
        "keywords": "Junior Developer",
        "location": "Latin America",
        "experience_levels": [1, 2],
        "remote": True,
        "time_posted": "1h",
        "max_results": 100
    },
    
]


SEARCH_TEMPLATES_UNUSED = [
]