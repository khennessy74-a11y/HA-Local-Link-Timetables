"""Tests for service-day-aware departure calculations."""

import importlib.util
from datetime import datetime
from pathlib import Path
import unittest

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "local_link_timetables"
    / "service_schedule.py"
)
SPEC = importlib.util.spec_from_file_location("local_link_service_schedule", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
SCHEDULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SCHEDULE)
next_departure = SCHEDULE.next_departure


class ServiceScheduleTests(unittest.TestCase):
    """Ensure the next-departure calculation respects configured operating days."""

    def test_next_departure_today(self):
        self.assertEqual(
            next_departure(["06:57", "08:23"], datetime(2026, 10, 26, 7, 0), ["0", "1"]),
            ("08:23", 83, "2026-10-26"),
        )

    def test_after_last_departure_skips_non_service_day(self):
        # Monday at 21:00, with service configured only Monday and Wednesday.
        self.assertEqual(
            next_departure(["06:57", "20:42"], datetime(2026, 10, 26, 21, 0), ["0", "2"]),
            ("06:57", 2017, "2026-10-28"),
        )

    def test_weekday_schedule_does_not_roll_into_sunday(self):
        # Saturday at 21:00: next weekday service is Monday morning.
        self.assertEqual(
            next_departure(["06:57", "20:42"], datetime(2026, 10, 31, 21, 0), ["0", "1", "2", "3", "4"]),
            ("06:57", 2017, "2026-11-02"),
        )

    def test_daily_route_preserves_existing_daily_behavior(self):
        self.assertEqual(
            next_departure(["06:57", "20:42"], datetime(2026, 10, 26, 21, 0), ["0", "1", "2", "3", "4", "5", "6"]),
            ("06:57", 597, "2026-10-27"),
        )

    def test_no_service_days_returns_no_departure(self):
        self.assertEqual(
            next_departure(["06:57"], datetime(2026, 10, 26, 7, 0), []),
            (None, None, None),
        )

    def test_minutes_until_rounds_up_for_partial_minute(self):
        self.assertEqual(
            next_departure(["08:00"], datetime(2026, 10, 26, 7, 59, 30), ["0"]),
            ("08:00", 1, "2026-10-26"),
        )


if __name__ == "__main__":
    unittest.main()
