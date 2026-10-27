"""Tests for service-day-aware departure calculations."""

import importlib.util
from datetime import date, datetime
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
departures_for_date = SCHEDULE.departures_for_date
holiday_dates_from_response = SCHEDULE.holiday_dates_from_response
validate_holiday_calendar_response = SCHEDULE.validate_holiday_calendar_response


class ServiceScheduleTests(unittest.TestCase):
    """Ensure the next-departure calculation respects configured operating days."""

    def test_calendar_response_extracts_all_day_and_timed_event_dates(self):
        response = {
            "calendar.public_holidays": {
                "events": [
                    {"start": "2026-12-25"},
                    {"start": "2027-01-01T00:00:00+00:00"},
                    {"start": "not-a-date"},
                    {"summary": "Missing start"},
                    None,
                ]
            }
        }
        self.assertEqual(
            holiday_dates_from_response(response, "calendar.public_holidays"),
            {"2026-12-25", "2027-01-01"},
        )

    def test_calendar_response_validation_accepts_valid_empty_calendar(self):
        validate_holiday_calendar_response(
            {"calendar.public_holidays": {"events": []}},
            "calendar.public_holidays",
        )

    def test_calendar_response_validation_rejects_missing_calendar_or_events(self):
        for response in (
            None,
            {},
            {"calendar.public_holidays": {}},
            {"calendar.public_holidays": {"events": "not-a-list"}},
        ):
            with self.subTest(response=response):
                with self.assertRaises(ValueError):
                    validate_holiday_calendar_response(
                        response, "calendar.public_holidays"
                    )

    def test_calendar_response_handles_missing_or_malformed_payload(self):
        self.assertEqual(holiday_dates_from_response(None, "calendar.holidays"), set())
        self.assertEqual(holiday_dates_from_response({}, "calendar.holidays"), set())
        self.assertEqual(
            holiday_dates_from_response(
                {"calendar.holidays": {"events": "unexpected"}}, "calendar.holidays"
            ),
            set(),
        )

    def test_departures_for_date_holiday_override_can_be_empty(self):
        self.assertEqual(
            departures_for_date(
                {0: ["06:30", "08:00"]},
                date(2026, 10, 26),
                ["0", "1", "2", "3", "4"],
                holiday_dates={"2026-10-26"},
                holiday_times=[],
            ),
            [],
        )

    def test_departures_for_date_uses_holiday_times_even_on_non_service_day(self):
        self.assertEqual(
            departures_for_date(
                {0: ["06:30"]},
                date(2026, 10, 27),
                ["0"],
                holiday_dates={"2026-10-27"},
                holiday_times=["09:15", "08:30"],
            ),
            ["08:30", "09:15"],
        )

    def test_departures_for_date_respects_weekday_schedule_and_options(self):
        self.assertEqual(
            departures_for_date(
                {0: ["08:00", "06:30"], 5: ["09:15"]},
                date(2026, 10, 31),
                ["0", "5"],
            ),
            ["09:15"],
        )
        self.assertEqual(
            departures_for_date({0: ["06:30"]}, date(2026, 10, 27), ["0"]),
            [],
        )

    def test_next_departure_today(self):
        self.assertEqual(
            next_departure(["06:57", "08:23"], datetime(2026, 10, 26, 7, 0), ["0", "1"]),
            ("08:23", 83, "2026-10-26"),
        )

    def test_after_last_departure_skips_non_service_day(self):
        # Monday at 21:00, with service configured only Monday and Wednesday.
        self.assertEqual(
            next_departure(["06:57", "20:42"], datetime(2026, 10, 26, 21, 0), ["0", "2"]),
            ("06:57", 2037, "2026-10-28"),
        )

    def test_weekday_schedule_does_not_roll_into_sunday(self):
        # Saturday at 21:00: next weekday service is Monday morning.
        self.assertEqual(
            next_departure(["06:57", "20:42"], datetime(2026, 10, 31, 21, 0), ["0", "1", "2", "3", "4"]),
            ("06:57", 2037, "2026-11-02"),
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

    def test_weekday_specific_schedule_uses_the_departures_for_that_day(self):
        schedule = {
            0: ["06:30", "08:00"],
            5: ["09:15"],
            6: ["10:45"],
        }
        self.assertEqual(
            next_departure(schedule, datetime(2026, 10, 31, 8, 0), ["0", "5", "6"]),
            ("09:15", 75, "2026-10-31"),
        )

    def test_weekday_specific_schedule_skips_days_with_no_schedule(self):
        schedule = {0: ["06:30"], 5: ["09:15"]}
        # Sunday has no configured schedule, so next service is Monday.
        self.assertEqual(
            next_departure(schedule, datetime(2026, 11, 1, 8, 0), ["0", "5", "6"]),
            ("06:30", 1350, "2026-11-02"),
        )

    def test_weekday_specific_schedule_does_not_reuse_weekday_times_on_sunday(self):
        schedule = {0: ["06:30"], 5: ["09:15"], 6: []}
        self.assertEqual(
            next_departure(schedule, datetime(2026, 11, 1, 8, 0), ["0", "5", "6"], search_days=0),
            (None, None, None),
        )


    def test_public_holiday_schedule_overrides_weekday_schedule(self):
        # Monday is normally a weekday service, but the calendar marks it
        # as a public holiday and the holiday timetable takes precedence.
        self.assertEqual(
            next_departure(
                {0: ["06:30", "08:00"], 1: ["07:00"]},
                datetime(2026, 10, 26, 7, 0),
                ["0", "1"],
                holiday_dates={"2026-10-26"},
                holiday_times=["09:15", "12:00"],
            ),
            ("09:15", 135, "2026-10-26"),
        )

    def test_holiday_schedule_can_operate_when_weekday_is_not_selected(self):
        self.assertEqual(
            next_departure(
                {0: ["06:30"]},
                datetime(2026, 10, 26, 7, 0),
                ["0"],
                holiday_dates={"2026-10-27"},
                holiday_times=["08:30"],
            ),
            ("08:30", 1530, "2026-10-27"),
        )

    def test_no_holiday_dates_preserves_ordinary_weekday_schedule(self):
        self.assertEqual(
            next_departure(
                {0: ["06:30", "08:00"]},
                datetime(2026, 10, 26, 7, 0),
                ["0"],
                holiday_times=["09:15"],
            ),
            ("08:00", 60, "2026-10-26"),
        )

    def test_departure_at_current_minute_is_still_available(self):
        self.assertEqual(
            next_departure(["08:00"], datetime(2026, 10, 26, 8, 0), ["0"]),
            ("08:00", 0, "2026-10-26"),
        )

    def test_invalid_weekday_numbers_are_rejected(self):
        with self.assertRaises(ValueError):
            next_departure(["08:00"], datetime(2026, 10, 26, 7, 0), ["7"])
        with self.assertRaises(ValueError):
            departures_for_date(["08:00"], date(2026, 10, 26), ["-1"])

    def test_empty_holiday_timetable_does_not_fall_back_to_weekday_times(self):
        self.assertEqual(
            next_departure(
                {0: ["06:30"]},
                datetime(2026, 10, 26, 7, 0),
                ["0"],
                holiday_dates={"2026-10-26"},
                holiday_times=[],
                search_days=0,
            ),
            (None, None, None),
        )

if __name__ == "__main__":
    unittest.main()
