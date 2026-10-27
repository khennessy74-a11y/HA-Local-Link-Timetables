"""Unit tests for the timetable parser, without requiring Home Assistant."""

import importlib.util
from pathlib import Path
import unittest

PARSER_PATH = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "local_link_timetables"
    / "parser.py"
)
SPEC = importlib.util.spec_from_file_location("local_link_timetable_parser", PARSER_PATH)
assert SPEC is not None and SPEC.loader is not None
PARSER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PARSER)
TimetableParseError = PARSER.TimetableParseError
AmbiguousTimetableError = PARSER.AmbiguousTimetableError
parse_departures = PARSER.parse_departures


class TimetableParserTests(unittest.TestCase):
    """Test common timetable row formats and duplicate-stop handling."""

    def test_route_188_kentstown_church(self):
        html = """
        <table><tr><td>Kentstown</td><td>Kentstown Church</td>
        <td>137851P/S06:5708:2311:2613:2615:2017:2019:3620:42</td></tr></table>
        """
        self.assertEqual(
            parse_departures(html, "Kentstown Church"),
            ["06:57", "08:23", "11:26", "13:26", "15:20", "17:20", "19:36", "20:42"],
        )

    def test_route_188_kennedy_road(self):
        html = """
        <table><tr><td>Navan</td><td>Kennedy Road</td>
        <td>189521P/S06:4507:5811:0513:0515:0517:0519:0520:47</td></tr></table>
        """
        self.assertEqual(
            parse_departures(html, "Kennedy Road"),
            ["06:45", "07:58", "11:05", "13:05", "15:05", "17:05", "19:05", "20:47"],
        )

    def test_case_and_whitespace_are_ignored(self):
        html = "<table><tr><td>KENNEDY   ROAD</td><td>06:45 07:58</td></tr></table>"
        self.assertEqual(parse_departures(html, "Kennedy Road"), ["06:45", "07:58"])

    def test_duplicate_stop_with_different_times_requires_hint(self):
        html = """
        <table>
          <tr><td>Direction North</td><td>Kennedy Road</td><td>06:45 07:58</td></tr>
          <tr><td>Direction South</td><td>Kennedy Road</td><td>08:45 09:58</td></tr>
        </table>
        """
        with self.assertRaises(AmbiguousTimetableError):
            parse_departures(html, "Kennedy Road")

    def test_direction_hint_selects_matching_row(self):
        html = """
        <table>
          <tr><td>Direction North</td><td>Kennedy Road</td><td>06:45 07:58</td></tr>
          <tr><td>Direction South</td><td>Kennedy Road</td><td>08:45 09:58</td></tr>
        </table>
        """
        self.assertEqual(
            parse_departures(html, "Kennedy Road", "south"),
            ["08:45", "09:58"],
        )

    def test_direction_heading_outside_table_selects_correct_row(self):
        html = """
        <h2>Outbound direction</h2>
        <table><tr><td>Balbriggan Station</td><td>06:20 · 07:30 · 09:40</td></tr></table>
        <h2>Return direction</h2>
        <table><tr><td>Balbriggan Station</td><td>08:45 · 11:45 · 14:45</td></tr></table>
        """
        self.assertEqual(
            parse_departures(html, "Balbriggan Station", "Return direction"),
            ["08:45", "11:45", "14:45"],
        )

    def test_middle_dot_separator_and_dash_placeholders(self):
        html = """
        <table><tr><td>Stop Name</td><td>Times</td></tr>
        <tr><td>Kells PCC</td><td>— · 09:15 · 13:00 · 16:00 · —</td></tr></table>
        """
        self.assertEqual(
            parse_departures(html, "Kells PCC"),
            ["09:15", "13:00", "16:00"],
        )


    def test_service_column_selects_only_matching_departures(self):
        html = """
        <h2>Enfield to Navan</h2>
        <table>
          <tr><th>Stop Name</th><th>Stop Location</th><th>Mon–Fri</th><th>Mon–Sun &amp; Public Holidays</th></tr>
          <tr><td>Enfield</td><td>Street Side Café</td><td>07:00</td><td>07:30 · 10:10 · 12:10</td></tr>
        </table>
        """
        self.assertEqual(
            parse_departures(html, "Enfield", service_column_hint="Mon–Fri"),
            ["07:00"],
        )
        self.assertEqual(
            parse_departures(html, "Enfield", service_column_hint="Mon–Sun & Public Holidays"),
            ["07:30", "10:10", "12:10"],
        )


    def test_grouped_service_column_includes_all_journeys(self):
        html = """
        <table>
          <tr><th>Stop Name</th><th colspan="2">Mon–Sat (2 journeys)</th><th>Sunday</th></tr>
          <tr><td>Navan</td><td>06:30</td><td>07:40</td><td>09:00</td></tr>
        </table>
        """
        self.assertEqual(
            parse_departures(html, "Navan", service_column_hint="Mon–Sat"),
            ["06:30", "07:40"],
        )

    def test_service_column_header_does_not_leak_between_tables(self):
        html = """
        <h2>Outbound</h2>
        <table>
          <tr><th>Stop Name</th><th>Mon–Fri</th><th>Sunday</th></tr>
          <tr><td>Shared Stop</td><td>06:30</td><td>09:00</td></tr>
        </table>
        <h2>Return</h2>
        <table>
          <tr><th>Stop Name</th><th>Saturday</th></tr>
          <tr><td>Shared Stop</td><td>15:30</td></tr>
        </table>
        """
        self.assertEqual(
            parse_departures(html, "Shared Stop", "Outbound", "Mon–Fri"),
            ["06:30"],
        )
        with self.assertRaises(TimetableParseError):
            parse_departures(html, "Shared Stop", "Return", "Mon–Fri")

    def test_route_189_style_weekday_and_holiday_columns(self):
        html = """
        <h2>Enfield to Navan</h2>
        <table>
          <tr><th>Stop Name</th><th>Stop Location</th><th>Mon–Fri</th><th>Mon–Sun &amp; Public Holidays</th></tr>
          <tr><td>Enfield</td><td>Street Side Café</td><td>07:00</td>
              <td>07:30 · 10:10 · 12:10 · 14:10</td></tr>
          <tr><td>Longwood</td><td>Main Street</td><td>07:10</td>
              <td>07:43 · 10:23 · 12:23 · 14:23</td></tr>
        </table>
        """
        self.assertEqual(
            parse_departures(html, "Longwood", service_column_hint="Mon–Fri"),
            ["07:10"],
        )
        self.assertEqual(
            parse_departures(
                html, "Longwood",
                service_column_hint="Mon–Sun & Public Holidays",
            ),
            ["07:43", "10:23", "12:23", "14:23"],
        )

    def test_unknown_service_column_raises(self):
        html = """
        <table>
          <tr><th>Stop Name</th><th>Mon–Fri</th></tr>
          <tr><td>Enfield</td><td>07:00</td></tr>
        </table>
        """
        with self.assertRaises(TimetableParseError):
            parse_departures(html, "Enfield", service_column_hint="Sunday only")

    def test_missing_stop_raises(self):
        with self.assertRaises(TimetableParseError):
            parse_departures(
                "<table><tr><td>Navan</td><td>06:45</td></tr></table>",
                "Kennedy Road",
            )


if __name__ == "__main__":
    unittest.main()
