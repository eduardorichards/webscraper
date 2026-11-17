"""Environment-specific configuration (12-factor).

Values come from environment variables, optionally loaded from a `.env` file in
the project root. Variables already set in the environment (e.g. by systemd)
take precedence over `.env`. Unset or empty variables fall back to the defaults
below. Invalid values raise ConfigError at import time.

Domain configuration (search templates, mappings, headers, keywords) lives in
config/settings.py and config/keyword_settings.py, not here.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Page sizes offered in the web UI (web_app.PER_PAGE_OPTIONS)
PER_PAGE_CHOICES = (25, 50, 100, 200)
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


class ConfigError(ValueError):
    """Raised when an environment variable has an invalid value."""


def _raw(environ, name):
    value = environ.get(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _int(environ, name, default, min_value=None, max_value=None):
    raw = _raw(environ, name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from None
    if min_value is not None and value < min_value:
        raise ConfigError(f"{name} must be >= {min_value}, got {value}")
    if max_value is not None and value > max_value:
        raise ConfigError(f"{name} must be <= {max_value}, got {value}")
    return value


def _float(environ, name, default, min_value=None):
    raw = _raw(environ, name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        raise ConfigError(f"{name} must be a number, got {raw!r}") from None
    if min_value is not None and value < min_value:
        raise ConfigError(f"{name} must be >= {min_value}, got {value}")
    return value


def _bool(environ, name, default):
    raw = _raw(environ, name)
    if raw is None:
        return default
    lowered = raw.lower()
    if lowered in _TRUE:
        return True
    if lowered in _FALSE:
        return False
    raise ConfigError(
        f"{name} must be a boolean (1/0, true/false, yes/no, on/off), got {raw!r}"
    )


def _choice(environ, name, default, choices, cast=str):
    raw = _raw(environ, name)
    if raw is None:
        return default
    try:
        value = cast(raw)
    except ValueError:
        value = None
    if value not in choices:
        allowed = ", ".join(str(c) for c in choices)
        raise ConfigError(f"{name} must be one of {allowed}, got {raw!r}")
    return value


def _path(environ, name, default):
    """Path setting; relative paths resolve from the project root."""
    path = Path(_raw(environ, name) or default)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def _delay_range(environ, prefix, default_min, default_max):
    min_name, max_name = f"{prefix}_MIN_DELAY", f"{prefix}_MAX_DELAY"
    min_delay = _float(environ, min_name, default_min, min_value=0)
    max_delay = _float(environ, max_name, default_max, min_value=0)
    if min_delay > max_delay:
        raise ConfigError(
            f"{min_name} ({min_delay}) must be <= {max_name} ({max_delay})"
        )
    return min_delay, max_delay


def load_settings(environ):
    """Parse and validate settings from a mapping of environment variables."""
    scrape_min, scrape_max = _delay_range(environ, "SCRAPE", 2, 4)
    search_min, search_max = _delay_range(environ, "SEARCH", 2, 4)
    ats_min, ats_max = _delay_range(environ, "ATS", 1, 2)
    return {
        # Web app
        "PORT": _int(environ, "PORT", 5000, min_value=1, max_value=65535),
        "HOST": _raw(environ, "HOST") or "0.0.0.0",
        "FLASK_DEBUG": _bool(environ, "FLASK_DEBUG", False),
        "DEFAULT_PER_PAGE": _choice(environ, "DEFAULT_PER_PAGE", 50,
                                    PER_PAGE_CHOICES, cast=int),
        # Storage and logging
        "DB_PATH": _path(environ, "DB_PATH", "data/database/jobs_master.db"),
        "LOG_DIR": _path(environ, "LOG_DIR", "data/logs"),
        "LOG_LEVEL": _choice(environ, "LOG_LEVEL", "INFO", LOG_LEVELS,
                             cast=str.upper),
        # Detail page scraping (rate limiting, ~10 min for 200 jobs)
        "SCRAPE_MIN_DELAY": scrape_min,
        "SCRAPE_MAX_DELAY": scrape_max,
        "BATCH_SIZE": _int(environ, "BATCH_SIZE", 50, min_value=1),
        "BATCH_PAUSE": _float(environ, "BATCH_PAUSE", 30, min_value=0),
        "RETRY_DELAY": _float(environ, "RETRY_DELAY", 60, min_value=0),
        "MAX_RETRIES": _int(environ, "MAX_RETRIES", 3, min_value=0),
        # Delay between search templates and between result pages
        "SEARCH_MIN_DELAY": search_min,
        "SEARCH_MAX_DELAY": search_max,
        # Result pages fetched per search template (first page + "See more jobs")
        "SEARCH_MAX_PAGES": _int(environ, "SEARCH_MAX_PAGES", 4,
                                 min_value=1, max_value=100),
        # Delay between companies when reading ATS job boards (--source ats)
        "ATS_MIN_DELAY": ats_min,
        "ATS_MAX_DELAY": ats_max,
    }


def check_web_settings(settings):
    """Refuse unsafe web app settings.

    The Werkzeug debugger allows arbitrary code execution, so debug mode is only
    allowed when the server listens on a loopback address.
    """
    if settings["FLASK_DEBUG"] and settings["HOST"] not in LOCAL_HOSTS:
        raise ConfigError(
            f"FLASK_DEBUG=true is only allowed with HOST set to 127.0.0.1, "
            f"localhost or ::1 (got HOST={settings['HOST']!r}): the Werkzeug "
            f"debugger allows remote code execution"
        )


load_dotenv(PROJECT_ROOT / ".env", override=False)
_settings = load_settings(os.environ)

PORT = _settings["PORT"]
HOST = _settings["HOST"]
FLASK_DEBUG = _settings["FLASK_DEBUG"]
DEFAULT_PER_PAGE = _settings["DEFAULT_PER_PAGE"]
DB_PATH = _settings["DB_PATH"]
LOG_DIR = _settings["LOG_DIR"]
LOG_LEVEL = _settings["LOG_LEVEL"]
SCRAPE_MIN_DELAY = _settings["SCRAPE_MIN_DELAY"]
SCRAPE_MAX_DELAY = _settings["SCRAPE_MAX_DELAY"]
BATCH_SIZE = _settings["BATCH_SIZE"]
BATCH_PAUSE = _settings["BATCH_PAUSE"]
RETRY_DELAY = _settings["RETRY_DELAY"]
MAX_RETRIES = _settings["MAX_RETRIES"]
SEARCH_MIN_DELAY = _settings["SEARCH_MIN_DELAY"]
SEARCH_MAX_DELAY = _settings["SEARCH_MAX_DELAY"]
SEARCH_MAX_PAGES = _settings["SEARCH_MAX_PAGES"]
ATS_MIN_DELAY = _settings["ATS_MIN_DELAY"]
ATS_MAX_DELAY = _settings["ATS_MAX_DELAY"]
