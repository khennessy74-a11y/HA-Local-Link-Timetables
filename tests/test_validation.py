"""Tests for timetable URL validation and duplicate identity normalization."""

import importlib.util
from pathlib import Path
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "local_link_timetables"
PACKAGE = types.ModuleType("local_link_timetables")
PACKAGE.__path__ = [str(ROOT)]
sys.modules.setdefault("local_link_timetables", PACKAGE)
SPEC = importlib.util.spec_from_file_location(
    "local_link_timetables.validation", ROOT / "validation.py"
)
assert SPEC is not None and SPEC.loader is not None
VALIDATION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATION)


class TimetableUrlValidationTests(unittest.TestCase):
    def test_accepts_official_https_hosts_and_default_port(self):
        for url in (
            "https://locallinklmf.ie/tfi-route-188/",
            "https://www.locallinklmf.ie/tfi-route-188/",
            "https://routes.locallinklmf.ie/tfi-route-188/",
            "https://locallinklmf.ie:443/tfi-route-188/",
        ):
            with self.subTest(url=url):
                self.assertTrue(VALIDATION.valid_timetable_url(url))

    def test_rejects_non_https_and_non_official_hosts(self):
        for url in (
            "http://locallinklmf.ie/tfi-route-188/",
            "https://locallinklmf.ie.evil.test/tfi-route-188/",
            "https://evil.test/locallinklmf.ie/tfi-route-188/",
            "https://localhost/tfi-route-188/",
            "https://127.0.0.1/tfi-route-188/",
            "",
        ):
            with self.subTest(url=url):
                self.assertFalse(VALIDATION.valid_timetable_url(url))

    def test_rejects_credentials_and_unexpected_or_malformed_ports(self):
        for url in (
            "https://user@locallinklmf.ie/tfi-route-188/",
            "https://user:pass@locallinklmf.ie/tfi-route-188/",
            "https://locallinklmf.ie:8443/tfi-route-188/",
            "https://locallinklmf.ie:abc/tfi-route-188/",
            "https://locallinklmf.ie:/tfi-route-188/",
        ):
            with self.subTest(url=url):
                self.assertFalse(VALIDATION.valid_timetable_url(url))

    def test_rejects_whitespace_and_malformed_url_values(self):
        for url in (" https://locallinklmf.ie/tfi-route-188/", "https://locallinklmf.ie:99999/"):
            with self.subTest(url=url):
                self.assertFalse(VALIDATION.valid_timetable_url(url))
        self.assertFalse(VALIDATION.valid_timetable_url(None))


class ConfigValueValidationTests(unittest.TestCase):
    def valid_data(self):
        return {
            "stop_name": "Kentstown Church",
            "service_days": ["0", "2", "5"],
            "service_column": "Mon–Fri",
            "holiday_column": "",
            "holiday_calendar": "",
        }

    def test_accepts_valid_basic_configuration(self):
        self.assertIsNone(VALIDATION.validate_config_values(self.valid_data()))

    def test_rejects_missing_stop_or_empty_service_days(self):
        data = self.valid_data()
        data["stop_name"] = "  "
        self.assertEqual(VALIDATION.validate_config_values(data), "stop_name_required")
        data = self.valid_data()
        data["service_days"] = []
        self.assertEqual(VALIDATION.validate_config_values(data), "service_days")

    def test_rejects_invalid_weekday_values_and_wrong_container_type(self):
        for days in (["7"], ["-1"], ["weekday"], "012", None):
            with self.subTest(days=days):
                data = self.valid_data()
                data["service_days"] = days
                self.assertEqual(VALIDATION.validate_config_values(data), "service_days")

    def test_holiday_column_requires_ordinary_column_and_calendar(self):
        data = self.valid_data()
        data["holiday_column"] = "Public Holidays"
        self.assertEqual(
            VALIDATION.validate_config_values(data),
            "holiday_calendar_required",
        )
        data["holiday_calendar"] = "calendar.public_holidays"
        data["service_column"] = ""
        self.assertEqual(
            VALIDATION.validate_config_values(data),
            "holiday_service_column_required",
        )

    def test_calendar_requires_holiday_column(self):
        data = self.valid_data()
        data["holiday_calendar"] = "calendar.public_holidays"
        self.assertEqual(
            VALIDATION.validate_config_values(data),
            "holiday_column_required",
        )


class EntryIdentityTests(unittest.TestCase):
    def test_identity_ignores_case_spacing_and_trailing_slash(self):
        first = {
            "url": "https://locallinklmf.ie/tfi-route-188/",
            "stop_name": "Kentstown   Church",
            "direction_hint": "Outbound",
            "service_column": "Mon–Fri",
        }
        second = {
            "url": "HTTPS://LOCALLINKLMF.IE/TFI-ROUTE-188",
            "stop_name": " kentstown church ",
            "direction_hint": "OUTBOUND",
            "service_column": "mon–fri",
        }
        self.assertEqual(
            VALIDATION.entry_identity(first),
            VALIDATION.entry_identity(second),
        )

    def test_identity_keeps_different_stop_and_service_column_distinct(self):
        base = {
            "url": "https://locallinklmf.ie/tfi-route-188/",
            "stop_name": "Kentstown Church",
            "direction_hint": "Outbound",
            "service_column": "Mon–Fri",
        }
        different = {**base, "stop_name": "Navan"}
        self.assertNotEqual(
            VALIDATION.entry_identity(base),
            VALIDATION.entry_identity(different),
        )


if __name__ == "__main__":
    unittest.main()
