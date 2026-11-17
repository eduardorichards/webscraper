"""Configuration for keyword matching and detail page scraping."""

# Rate limiting settings (delays, batch size, retries) are environment config:
# see config/env.py.

# User agent rotation pool
USER_AGENTS = [
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0',
]

# Keywords for the current CV: Java/Spring Boot and Python backend, QA automation,
# AWS and AI products. Matched case-insensitively on word boundaries.
DEFAULT_KEYWORDS = [
    "software", "developer", "programming", "database", "microservices", 
    "Backend", "Java", "Spring", "Spring Boot", "SQL", "PostgreSQL", 
    "MySQL", "Git", "Github", "GitLab", "Node.js", "Angular", "Python", 
    "JavaScript", "TypeScript", "Elasticsearch", "Docker", "SQLite", 
    "Redis", "Graphana", "Kibana", "Monitoring", "metrics", "Cybersecurity", 
    "OpenTelemetry", "AI", "IA", "LLM", "LLms", "Automated Testing", 
    "Testing", "Automation Testing", "QA", "Architecture", "JUnit", 
    "Mockito", "Agile", "Scrum", "SDLC", "JWT", "OAuth 2.0", "Full Stack", 
    "Site Reliability Engineer", "SRE", "API", "Restful", "Devops", "Claude", "OpenAI", "Gemini", "Cursor", "Anthropic", "Agentic", "Semi", "Ssr", "Semisenior",
    "Software Developer",
    # QA automation
    "QA Automation", "SDET", "Playwright", "Selenium", "REST Assured", "TestNG", "Postman",
    # AWS / cloud / CI
    "AWS", "Lambda", "DynamoDB", "ECS", "S3", "Serverless", "Terraform", "Kubernetes",
    "GitHub Actions", "Jenkins",
    # AI tooling
    "MCP", "Prompt Engineering", "Claude Code", "Copilot",
]

# Keys must match a DEFAULT_KEYWORDS entry exactly (case-sensitive): weights are
# looked up by keyword, so any other key is silently ignored.
# Strategic weights: Prioritizing Java, Testing frameworks, and Backend Architecture
WEIGHTED_KEYWORDS = {
    "Java": 10,                # Your primary specialty
    "Spring Boot": 10,         # Critical for Java Backend roles
    "JUnit": 8,               # Core for Automated Testing
    "Mockito": 8,             # Vital for Mock-based testing in Java
    "Semi": 10,
    "Semisenior": 10,
    "Ssr": 10,
    "Backend": 8,
    "Automated Testing": 3,   # High signal for your current studies
    "microservices": 4,       # High-value architecture keyword
    "PostgreSQL": 4,          # Specific DBs weigh more than "SQL"
    "Docker": 3,              # Essential for modern deployment
    "OAuth 2.0": 2,           # Shows security maturity
    "OpenTelemetry": 3,       # Deep backend/monitoring knowledge
    "SRE": 3,                 # Good for cross-disciplinary roles
    "SQL": 3,
    "Spring": 4,
    "AI": 2,
    "Python": 5,
    "Git": 2,
    "Software Developer": 4,
    "Cybersecurity": 3,
    "SDLC": 4,
    "Full Stack": 3,
    # QA automation
    "QA Automation": 8,
    "Playwright": 8,
    "SDET": 7,
    "REST Assured": 7,
    "Selenium": 7,
    "TestNG": 5,
    "Postman": 3,
    # AWS / cloud / CI
    # AWS services kept low so an AWS-heavy posting can't stack them
    "AWS": 6,
    "Lambda": 3,
    "Serverless": 3,
    "DynamoDB": 2,
    "ECS": 2,
    "S3": 2,
    "Terraform": 3,
    "Kubernetes": 3,
    "GitHub Actions": 3,
    "Jenkins": 2,
    # AI
    "LLM": 7,
    "MCP": 6,
    "Prompt Engineering": 4,
    "Claude Code": 4,
    "Copilot": 2,
    "TypeScript": 3,
}
