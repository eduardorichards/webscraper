"""Tests for the "above my level" seniority rule."""

import unittest

from config.settings import SENIORITY_ORDER, TARGET_SENIORITY_LEVELS
from utils.seniority import levels_above, title_above_level
from utils.sqlite_storage import SQLiteStorage


class TestLevelsAbove(unittest.TestCase):

    def test_order_matches_linkedin_values(self):
        self.assertEqual(SENIORITY_ORDER, ["Internship", "Entry level", "Associate",
                                           "Mid-Senior level", "Director", "Executive"])

    def test_default_targets(self):
        self.assertEqual(TARGET_SENIORITY_LEVELS, ["Internship", "Entry level", "Associate"])
        self.assertEqual(SQLiteStorage.ABOVE_TARGET_LEVELS,
                         ["Mid-Senior level", "Director", "Executive"])

    def test_highest_target_wins(self):
        self.assertEqual(levels_above(["Entry level"]),
                         ["Associate", "Mid-Senior level", "Director", "Executive"])
        self.assertEqual(levels_above(["Internship", "Director"]), ["Executive"])
        self.assertEqual(levels_above(["Executive"]), [])

    def test_empty_targets_hide_nothing(self):
        self.assertEqual(levels_above([]), [])

    def test_unknown_target_rejected(self):
        with self.assertRaisesRegex(ValueError, "Senior"):
            levels_above(["Senior"])


class TestTitleAboveLevel(unittest.TestCase):

    def test_above_level_titles(self):
        for title in ("Lead Engineer, DevOps Platform & Security (m/f/d)",
                      "Director, AI Engineering - Tech Lead (m/f/d)",
                      "Programador Senior Backend", "Desarrollador Sénior Java",
                      "Desenvolvedor Java SR", "Developer Sr. Analyst - FullStack",
                      "Técnico Líder .Net", "Team Leader QA", "Head of Ontology",
                      "Staff Product Security Engineer", "Principal Engineer",
                      "Senior Backend Architect Latam", "Arquitecta de Soluciones",
                      "Engineering Manager/Tech Lead", "Gerente de Sistemas",
                      "Jefe de Desarrollo", "SENIOR PYTHON DEVELOPER"):
            with self.subTest(title=title):
                self.assertTrue(title_above_level(title))

    def test_target_level_titles(self):
        for title in ("Backend Developer", "QA Automation Engineer",
                      "Desarrollador Python Ssr", "Semi Senior Java Developer",
                      "Semi-Senior QA Analyst", "Semisenior Backend",
                      "QA Automatizador SSR o SR", "Developer Jr/Ssr/Sr",
                      "Junior to Senior Software Engineer", "Software Developer In Test II",
                      "Analista de AppSec PLENO", None, ""):
            with self.subTest(title=title):
                self.assertFalse(title_above_level(title))

    def test_word_boundaries(self):
        # Terms inside longer words are not matches
        for title in ("Staffing Coordinator", "Leading-edge Python Developer",
                      "Headless CMS Developer", "Srini's Startup Developer",
                      "Directorio Web Developer", "Managerial Accounting Intern"):
            with self.subTest(title=title):
                self.assertFalse(title_above_level(title))


if __name__ == '__main__':
    unittest.main()
