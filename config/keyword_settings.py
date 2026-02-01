"""Configuration for keyword matching and detail page scraping."""

# Rate limiting settings (~10 min for 200 jobs)
SCRAPE_MIN_DELAY = 2      # seconds minimum delay between requests
SCRAPE_MAX_DELAY = 4      # seconds maximum delay (avg = 3s)
BATCH_SIZE = 50           # jobs per batch before pause
BATCH_PAUSE = 30          # seconds pause between batches
RETRY_DELAY = 60          # seconds wait on 429 error
MAX_RETRIES = 3           # max retries per job on rate limit

# User agent rotation pool
USER_AGENTS = [
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0',
]

# Updated keywords based on your Java Backend and Automated Testing focus
DEFAULT_KEYWORDS = [
    "software", "developer", "programming", "database", "microservices", 
    "Backend", "Java", "Spring", "Spring Boot", "SQL", "PostgreSQL", 
    "MySQL", "Git", "Github", "GitLab", "Node.js", "Angular", "Python", 
    "JavaScript", "Typescript", "Elasticsearch", "Docker", "SQLite", 
    "Redis", "Graphana", "Kibana", "Monitoring", "metrics", "Cybersecurity", 
    "Open Telemetry", "AI", "IA", "LLM", "LLms", "Automated Testing", 
    "Testing", "Automation Testing", "QA", "Architecture", "JUnit", 
    "Mockito", "Agile", "Scrum", "SDLC", "JWT", "OAuth 2.0", "Full Stack", 
    "Site Reliability Engineer", "SRE", "API", "Restful", "Devops"
]

# Strategic weights: Prioritizing Java, Testing frameworks, and Backend Architecture
WEIGHTED_KEYWORDS = {
    "Java": 2.5,                # Your primary specialty
    "Spring Boot": 2.2,         # Critical for Java Backend roles
    "JUnit": 2.0,               # Core for Automated Testing
    "Mockito": 2.0,             # Vital for Mock-based testing in Java
    "Automated Testing": 1.8,   # High signal for your current studies
    "Microservices": 1.5,       # High-value architecture keyword
    "PostgreSQL": 1.4,          # Specific DBs weigh more than "SQL"
    "Docker": 1.3,              # Essential for modern deployment
    "OAuth 2.0": 1.2,           # Shows security maturity
    "Open Telemetry": 1.2,      # Deep backend/monitoring knowledge
    "SRE": 1.0,                 # Good for cross-disciplinary roles
}
