"""Application settings and configuration"""

# LinkedIn scraping settings
LINKEDIN_BASE_URL = "https://www.linkedin.com/jobs/search/"
# Guest endpoint behind the "See more jobs" button: same query params as the
# search page plus start=<cards already shown>. Returns bare job cards.
LINKEDIN_SEE_MORE_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
# Cards per page (observed 2026-11-14). A page with fewer cards is the last one.
SEARCH_FIRST_PAGE_SIZE = 60
SEARCH_MORE_PAGE_SIZE = 10

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

# Seniority levels shown on job pages (job_posts.seniority_level), lowest first
SENIORITY_ORDER = [EXPERIENCE_LEVELS[level] for level in sorted(EXPERIENCE_LEVELS)]

# Levels I'm targeting. Jobs whose seniority_level ranks above the highest of
# these are hidden by the web UI's "Hide above my level" filter. Unranked
# values ("Not Applicable", NULL) are never hidden.
TARGET_SENIORITY_LEVELS = ["Internship", "Entry level", "Associate"]

# The same filter also checks the title, since seniority_level is often "Not
# Applicable" on senior postings. Regex fragments, matched case-insensitively
# as whole words (English, Spanish, and Portuguese spellings of Senior).
ABOVE_LEVEL_TITLE_TERMS = [
    r"s[eéê]nior", r"sr", r"lead", r"leader", r"l[ií]der", r"directora?",
    r"head", r"staff", r"principal", r"architect", r"arquitect[oa]",
    r"manager", r"gerente", r"jef[ea]",
]
# A title naming one of these is never hidden, even if it also has an
# above-level term ("QA Automatizador SSR o SR", "Developer Jr/Ssr/Sr")
TARGET_LEVEL_TITLE_TERMS = [
    r"j[uú]nior", r"jr", r"semi[\s-]?s[eé]nior", r"ssr", r"trainee",
    r"intern", r"internship", r"pasante",
]

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


def _search_pair(group, keywords):
    """One search group run twice: Argentina (any work mode) and Latin America remote."""
    common = {
        "keywords": keywords,
        "experience_levels": [1, 2, 3],  # Internship, Entry level, Associate
        # Twice the hourly cron interval, so consecutive runs overlap: a posting
        # isn't lost to a late or skipped run. Repeat hits only add job_searches
        # rows; jobs that already have a job_posts row aren't fetched again.
        "time_posted": "2h",
        "max_results": 250,
    }
    return [
        dict(common, name=f"{group} AR", location="Argentina", remote=False),
        dict(common, name=f"{group} LATAM", location="Latin America", remote=True),
    ]


# List order = priority: main.multiple_search() runs them top to bottom.
# One term per template: the logged-out search doesn't honor OR (checked
# 2026-11-17: '"QA Automation" OR SDET' returned 4,000+ results vs 7,000+ for
# SDET alone), and its matching is fuzzy enough that a term also surfaces
# close variants (SDET -> "QA Automation", "Software Engineer in Test").
SEARCH_TEMPLATES = [
    # --- Tier 1: Java backend, QA automation, AI/LLM, backend ---
    *_search_pair("Java", "Java"),
    *_search_pair("QA Automation", "QA Automation"),
    *_search_pair("Automatizador", "Automatizador"),
    *_search_pair("AI Engineer", "AI Engineer"),
    *_search_pair("LLM", "LLM"),
    *_search_pair("Backend", "Backend"),
    # --- Tier 2: Python, AWS, testing tools ---
    *_search_pair("Python", "Python"),
    *_search_pair("AWS", "AWS"),
    *_search_pair("Playwright", "Playwright"),
    # --- Tier 3: fullstack, generic, DevOps ---
    *_search_pair("Fullstack", "Fullstack"),
    *_search_pair("Software Developer", "Software Developer"),
    *_search_pair("DevOps", "DevOps"),
]


SEARCH_TEMPLATES_UNUSED = [
]