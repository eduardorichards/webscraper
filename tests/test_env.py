"""Tests for environment configuration (config/env.py)"""

import unittest
from pathlib import Path

from config.env import (
    PROJECT_ROOT,
    ConfigError,
    check_web_settings,
    load_settings,
)


class TestDefaults(unittest.TestCase):
    """An empty environment gives the previously hardcoded values"""

    def test_defaults(self):
        settings = load_settings({})
        self.assertEqual(settings, {
            "PORT": 5000,
            "HOST": "0.0.0.0",
            "FLASK_DEBUG": False,
            "DEFAULT_PER_PAGE": 50,
            "DB_PATH": PROJECT_ROOT / "data" / "database" / "jobs_master.db",
            "LOG_DIR": PROJECT_ROOT / "data" / "logs",
            "LOG_LEVEL": "INFO",
            "SCRAPE_MIN_DELAY": 2,
            "SCRAPE_MAX_DELAY": 4,
            "BATCH_SIZE": 50,
            "BATCH_PAUSE": 30,
            "RETRY_DELAY": 60,
            "MAX_RETRIES": 3,
            "SEARCH_MIN_DELAY": 2,
            "SEARCH_MAX_DELAY": 4,
        })

    def test_empty_values_use_defaults(self):
        """A blank `KEY=` line in .env counts as unset"""
        self.assertEqual(load_settings({"PORT": "", "HOST": "  "}),
                         load_settings({}))

    def test_default_web_settings_are_allowed(self):
        check_web_settings(load_settings({}))


class TestOverrides(unittest.TestCase):
    """Environment variables override the defaults"""

    def test_web_overrides(self):
        settings = load_settings({
            "PORT": "8080",
            "HOST": "127.0.0.1",
            "FLASK_DEBUG": "true",
            "DEFAULT_PER_PAGE": "100",
        })
        self.assertEqual(settings["PORT"], 8080)
        self.assertEqual(settings["HOST"], "127.0.0.1")
        self.assertIs(settings["FLASK_DEBUG"], True)
        self.assertEqual(settings["DEFAULT_PER_PAGE"], 100)

    def test_bool_values(self):
        for raw in ("1", "true", "TRUE", "yes", "on"):
            self.assertIs(load_settings({"FLASK_DEBUG": raw})["FLASK_DEBUG"], True)
        for raw in ("0", "false", "False", "no", "off"):
            self.assertIs(load_settings({"FLASK_DEBUG": raw})["FLASK_DEBUG"], False)

    def test_relative_paths_resolve_from_project_root(self):
        settings = load_settings({"DB_PATH": "other/jobs.db", "LOG_DIR": "logs"})
        self.assertEqual(settings["DB_PATH"], PROJECT_ROOT / "other" / "jobs.db")
        self.assertEqual(settings["LOG_DIR"], PROJECT_ROOT / "logs")

    def test_absolute_paths_are_kept(self):
        settings = load_settings({"DB_PATH": "/srv/jobs.db", "LOG_DIR": "/var/log/js"})
        self.assertEqual(settings["DB_PATH"], Path("/srv/jobs.db"))
        self.assertEqual(settings["LOG_DIR"], Path("/var/log/js"))

    def test_log_level_is_case_insensitive(self):
        self.assertEqual(load_settings({"LOG_LEVEL": "debug"})["LOG_LEVEL"], "DEBUG")

    def test_scraping_overrides(self):
        settings = load_settings({
            "SCRAPE_MIN_DELAY": "0.5",
            "SCRAPE_MAX_DELAY": "1.5",
            "BATCH_SIZE": "10",
            "BATCH_PAUSE": "5",
            "RETRY_DELAY": "120",
            "MAX_RETRIES": "0",
            "SEARCH_MIN_DELAY": "3",
            "SEARCH_MAX_DELAY": "3",
        })
        self.assertEqual(settings["SCRAPE_MIN_DELAY"], 0.5)
        self.assertEqual(settings["SCRAPE_MAX_DELAY"], 1.5)
        self.assertEqual(settings["BATCH_SIZE"], 10)
        self.assertEqual(settings["BATCH_PAUSE"], 5)
        self.assertEqual(settings["RETRY_DELAY"], 120)
        self.assertEqual(settings["MAX_RETRIES"], 0)
        self.assertEqual(settings["SEARCH_MIN_DELAY"], 3)
        self.assertEqual(settings["SEARCH_MAX_DELAY"], 3)


class TestInvalidValues(unittest.TestCase):
    """Invalid values raise ConfigError naming the variable"""

    def assertConfigError(self, environ, *fragments):
        with self.assertRaises(ConfigError) as ctx:
            load_settings(environ)
        for fragment in fragments:
            self.assertIn(fragment, str(ctx.exception))

    def test_non_integer_port(self):
        self.assertConfigError({"PORT": "abc"}, "PORT must be an integer", "'abc'")

    def test_port_out_of_range(self):
        self.assertConfigError({"PORT": "70000"}, "PORT", "65535")
        self.assertConfigError({"PORT": "0"}, "PORT", ">= 1")

    def test_invalid_bool(self):
        self.assertConfigError({"FLASK_DEBUG": "maybe"}, "FLASK_DEBUG", "'maybe'")

    def test_invalid_log_level(self):
        self.assertConfigError({"LOG_LEVEL": "LOUD"}, "LOG_LEVEL", "INFO", "'LOUD'")

    def test_per_page_not_an_option(self):
        self.assertConfigError({"DEFAULT_PER_PAGE": "33"}, "DEFAULT_PER_PAGE", "25, 50, 100, 200")
        self.assertConfigError({"DEFAULT_PER_PAGE": "abc"}, "DEFAULT_PER_PAGE")

    def test_non_numeric_delay(self):
        self.assertConfigError({"SCRAPE_MIN_DELAY": "fast"}, "SCRAPE_MIN_DELAY must be a number")

    def test_negative_delay(self):
        self.assertConfigError({"RETRY_DELAY": "-1"}, "RETRY_DELAY", ">= 0")

    def test_zero_batch_size(self):
        self.assertConfigError({"BATCH_SIZE": "0"}, "BATCH_SIZE", ">= 1")

    def test_min_delay_above_max(self):
        self.assertConfigError({"SCRAPE_MIN_DELAY": "5"}, "SCRAPE_MIN_DELAY", "SCRAPE_MAX_DELAY")
        self.assertConfigError({"SEARCH_MIN_DELAY": "3", "SEARCH_MAX_DELAY": "1"},
                               "SEARCH_MIN_DELAY", "SEARCH_MAX_DELAY")


class TestWebSafety(unittest.TestCase):
    """Debug mode is refused unless bound to a loopback address"""

    def test_debug_on_public_host_is_refused(self):
        for host in ("0.0.0.0", "192.168.1.10", "example.com"):
            settings = load_settings({"FLASK_DEBUG": "true", "HOST": host})
            with self.assertRaises(ConfigError) as ctx:
                check_web_settings(settings)
            self.assertIn("FLASK_DEBUG", str(ctx.exception))
            self.assertIn("remote code execution", str(ctx.exception))

    def test_debug_on_default_host_is_refused(self):
        with self.assertRaises(ConfigError):
            check_web_settings(load_settings({"FLASK_DEBUG": "1"}))

    def test_debug_on_loopback_is_allowed(self):
        for host in ("127.0.0.1", "localhost", "::1"):
            check_web_settings(load_settings({"FLASK_DEBUG": "true", "HOST": host}))

    def test_public_host_without_debug_is_allowed(self):
        check_web_settings(load_settings({"HOST": "0.0.0.0", "FLASK_DEBUG": "false"}))


if __name__ == "__main__":
    unittest.main()
