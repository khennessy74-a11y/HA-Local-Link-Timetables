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
parse_holiday_departures = PARSER.parse_holiday_departures


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

    def test_invalid_clock_values_are_not_partially_parsed(self):
        html = """
        <table><tr><td>Stop Name</td><td>Times</td></tr>
        <tr><td>Kells PCC</td><td>25:00 · 123:45 · 06:30 · 7:05</td></tr></table>
        """
        self.assertEqual(parse_departures(html, "Kells PCC"), ["06:30", "07:05"])

    def test_tightly_concatenated_valid_times_still_parse(self):
        html = """
        <table><tr><td>Kells PCC</td><td>06:3007:4518:05</td></tr></table>
        """
        self.assertEqual(
            parse_departures(html, "Kells PCC"), ["06:30", "07:45", "18:05"]
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

    def test_route_188_grouped_headers_select_the_correct_journey_group(self):
        html = """
        <h2>Drogheda to Navan to Athboy</h2>
        <table>
          <tr>
            <th>Stop Name</th><th>Stop Location</th><th>Stop Number</th><th>Restriction</th>
            <th colspan="2">Mon–Sat (1 journey)</th>
            <th colspan="6">Monday–Sunday (7 journeys)</th>
          </tr>
          <tr>
            <th></th><th></th><th></th><th></th>
            <th>1</th><th>2</th><th>1</th><th>2</th><th>3</th><th>4</th><th>5</th><th>6</th>
          </tr>
          <tr>
            <td>Kentstown</td><td>Kentstown Church</td><td>137851</td><td>P/S</td>
            <td>06:57</td><td>08:23</td><td>11:26</td><td>13:26</td><td>15:20</td>
            <td>17:20</td><td>19:36</td><td>20:42</td>
          </tr>
        </table>
        """
        self.assertEqual(
            parse_departures(html, "Kentstown Church", service_column_hint="Mon–Sat"),
            ["06:57", "08:23"],
        )
        self.assertEqual(
            parse_departures(
                html, "Kentstown Church",
                service_column_hint="Monday–Sunday",
            ),
            ["11:26", "13:26", "15:20", "17:20", "19:36", "20:42"],
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

    def test_stop_name_containing_weekday_is_not_mistaken_for_header(self):
        html = """
        <table>
          <tr><th>Stop Name</th><th>Mon–Fri</th></tr>
          <tr><td>Sunday Market</td><td>08:15 · 12:45</td></tr>
        </table>
        """
        self.assertEqual(
            parse_departures(html, "Sunday Market", service_column_hint="Mon–Fri"),
            ["08:15", "12:45"],
        )

    def test_missing_stop_raises(self):
        with self.assertRaises(TimetableParseError):
            parse_departures(
                "<table><tr><td>Navan</td><td>06:45</td></tr></table>",
                "Kennedy Road",
            )


    def test_route_195_outbound_single_service_column(self):
        """Route 195 outbound uses a single Sunday/holiday service column."""
        html = """
        <h2>Ashbourne to Balbriggan</h2>
        <table>
          <tr><th>Stop Name</th><th>Stop Location</th><th>Stop No</th>
              <th>Monday – Sunday &amp; Public Holidays</th></tr>
          <tr><td>Ashbourne</td><td>Town Centre</td><td>12345</td>
              <td>07:30 · 10:30 · 13:30 · 16:15 · 18:45 · 22:05</td></tr>
        </table>
        """
        self.assertEqual(
            parse_departures(
                html, "Ashbourne",
                service_column_hint="Monday – Sunday & Public Holidays",
            ),
            ["07:30", "10:30", "13:30", "16:15", "18:45", "22:05"],
        )

    def test_route_195_return_distinguishes_weekday_and_sunday_columns(self):
        """Route 195 return has separate Mon–Sat and Sunday/holiday columns."""
        html = """
        <h2>Balbriggan to Ashbourne</h2>
        <table>
          <tr><th>Stop Name</th><th>Stop Location</th><th>Stop No</th>
              <th>Mon–Sat</th><th>Monday – Sunday &amp; Public Holidays</th></tr>
          <tr><td>Balbriggan Station</td><td>Railway Street</td><td>12345</td>
              <td>—</td><td>08:45 · 11:45 · 14:45 · 17:25 · 20:25</td></tr>
          <tr><td>Balbriggan Library</td><td>Main Street</td><td>12346</td>
              <td>08:50 · 11:50</td><td>08:50 · 11:50 · 14:50</td></tr>
        </table>
        """
        self.assertEqual(
            parse_departures(
                html, "Balbriggan Station",
                direction_hint="Balbriggan to Ashbourne",
                service_column_hint="Monday – Sunday & Public Holidays",
            ),
            ["08:45", "11:45", "14:45", "17:25", "20:25"],
        )
        self.assertEqual(
            parse_departures(
                html, "Balbriggan Library",
                service_column_hint="Mon–Sat",
            ),
            ["08:50", "11:50"],
        )

    def test_route_195_empty_selected_service_column_does_not_fall_back(self):
        """A dash in the selected column must not leak times from another service."""
        html = """
        <table>
          <tr><th>Stop Name</th><th>Mon–Sat</th><th>Sunday</th></tr>
          <tr><td>Balbriggan Station</td><td>—</td><td>08:45 · 11:45</td></tr>
        </table>
        """
        with self.assertRaises(TimetableParseError):
            parse_departures(
                html, "Balbriggan Station", service_column_hint="Mon–Sat"
            )

    def test_service_column_does_not_use_header_from_another_table(self):
        html = """
        <h2>Outbound</h2>
        <table>
          <tr><th>Stop Name</th><th>Mon–Fri</th></tr>
          <tr><td>Shared Stop</td><td>06:30</td></tr>
        </table>
        <h2>Return</h2>
        <table>
          <tr><th>Stop Name</th><th>Saturday</th></tr>
          <tr><td>Shared Stop</td><td>15:30</td></tr>
        </table>
        """
        with self.assertRaises(TimetableParseError):
            parse_departures(html, "Shared Stop", "Return", "Mon–Fri")


    def test_exact_stop_match_does_not_confuse_similarly_named_stops(self):
        html = """
        <table>
          <tr><td>Newtown</td><td>06:15</td></tr>
          <tr><td>Newtown Cross</td><td>07:25</td></tr>
        </table>
        """
        self.assertEqual(parse_departures(html, "Newtown"), ["06:15"])

    def test_stop_match_is_case_insensitive_and_whitespace_tolerant(self):
        html = """
        <table>
          <tr><td>St. Peter's   Church</td><td>06:15 · 07:25</td></tr>
        </table>
        """
        self.assertEqual(
            parse_departures(html, "ST. PETER'S Church"),
            ["06:15", "07:25"],
        )

    def test_direction_hint_uses_word_boundaries(self):
        html = """
        <h2>Outbound</h2>
        <table><tr><td>Newtown</td><td>06:15</td></tr></table>
        <h2>Return</h2>
        <table><tr><td>Newtown</td><td>07:25</td></tr></table>
        """
        self.assertEqual(
            parse_departures(html, "Newtown", "Return"),
            ["07:25"],
        )



    def test_route_lh701_combines_services_within_selected_direction(self):
        html = """
        <h2>Dundalk → Carlingford</h2>
        <h3>Service 1</h3>
        <table><tr><td>Dundalk</td><td>10:45</td></tr></table>
        <h3>Service 2</h3>
        <table><tr><td>Dundalk</td><td>13:45</td></tr></table>
        <h3>Service 3</h3>
        <table><tr><td>Dundalk</td><td>16:45</td></tr></table>
        <h2>Carlingford → Dundalk</h2>
        <h3>Service 1</h3>
        <table><tr><td>Dundalk</td><td>12:10</td></tr></table>
        <h3>Service 2</h3>
        <table><tr><td>Dundalk</td><td>15:10</td></tr></table>
        <h3>Service 3</h3>
        <table><tr><td>Dundalk</td><td>18:10</td></tr></table>
        """
        self.assertEqual(
            parse_departures(html, "Dundalk", "Dundalk → Carlingford"),
            ["10:45", "13:45", "16:45"],
        )
        self.assertEqual(
            parse_departures(html, "Dundalk", "Carlingford → Dundalk"),
            ["12:10", "15:10", "18:10"],
        )

    def test_weekday_sections_are_not_combined_without_day_selection(self):
        html = """
        <h2>Thursday – Outbound</h2>
        <table><tr><td>Longwood</td><td>09:00</td></tr></table>
        <h2>Friday – Outbound</h2>
        <table><tr><td>Longwood</td><td>10:30</td></tr></table>
        """
        with self.assertRaises(AmbiguousTimetableError):
            parse_departures(html, "Longwood", "Outbound")
        self.assertEqual(
            parse_departures(html, "Longwood", "Thursday"),
            ["09:00"],
        )


    def test_route_177_grouped_mon_sat_and_sunday_columns(self):
        html = """
        <h2>Ardee → Kells</h2>
        <table>
          <tr><th>Stop Name</th><th>Stop Location</th><th>Stop Number</th>
              <th>Mon-Sat</th><th colspan="4">Monday - Sunday &amp; Public Holidays</th></tr>
          <tr><td>Ardee Bypass</td><td>Bypass Bus Stop</td><td>152461</td>
              <td>07:40</td><td>11:30</td><td>14:30</td><td>17:25</td><td>20:45</td></tr>
        </table>
        """
        self.assertEqual(
            parse_departures(html, "Ardee Bypass", service_column_hint="Mon-Sat"),
            ["07:40"],
        )
        self.assertEqual(
            parse_departures(
                html, "Ardee Bypass",
                service_column_hint="Monday - Sunday & Public Holidays",
            ),
            ["11:30", "14:30", "17:25", "20:45"],
        )

    def test_route_192_times_column(self):
        html = """
        <h2>Balbriggan → Swords</h2>
        <table>
          <tr><th>Stop Name</th><th>Stop Location</th><th>Stop No.</th><th>Times</th></tr>
          <tr><td>Balbriggan Station</td><td>Balbriggan Station</td><td>134741</td>
              <td>06:20 · 07:30 · 09:40 · 11:20 · 13:30 · 15:40 · 17:10 · 19:10 · 21:10 · 22:35</td></tr>
        </table>
        """
        self.assertEqual(
            parse_departures(html, "Balbriggan Station", "Balbriggan → Swords"),
            ["06:20", "07:30", "09:40", "11:20", "13:30", "15:40", "17:10", "19:10", "21:10", "22:35"],
        )


    def test_weekday_schedule_combines_columns_applicable_to_each_day(self):
        html = """
        <h2>Drogheda to Navan</h2>
        <table>
          <tr><th>Stop Name</th><th>Mon–Sat (1 journey)</th>
              <th colspan="2">Monday–Sunday (2 journeys)</th></tr>
          <tr><td>Kentstown Church</td><td>06:57</td><td>11:26</td><td>13:26</td></tr>
        </table>
        """
        schedule = PARSER.parse_weekday_departures(html, "Kentstown Church")
        self.assertIsNotNone(schedule)
        self.assertEqual(schedule[0], ["06:57", "11:26", "13:26"])
        self.assertEqual(schedule[5], ["06:57", "11:26", "13:26"])
        self.assertEqual(schedule[6], ["11:26", "13:26"])

    def test_weekday_range_keeps_additional_explicit_days(self):
        html = """
        <table>
          <tr><th>Stop Name</th><th>Mon–Fri &amp; Sunday</th></tr>
          <tr><td>Navan</td><td>06:30 · 08:30</td></tr>
        </table>
        """
        schedule = PARSER.parse_weekday_departures(html, "Navan")
        self.assertIsNotNone(schedule)
        for day in (0, 1, 2, 3, 4, 6):
            self.assertEqual(schedule[day], ["06:30", "08:30"])
        self.assertEqual(schedule[5], [])

    def test_weekday_range_accepts_written_to_and_keeps_extra_days(self):
        html = """
        <table>
          <tr><th>Stop Name</th><th>Monday to Friday &amp; Sunday</th></tr>
          <tr><td>Navan</td><td>06:30 · 08:30</td></tr>
        </table>
        """
        schedule = PARSER.parse_weekday_departures(html, "Navan")
        self.assertIsNotNone(schedule)
        for day in (0, 1, 2, 3, 4, 6):
            self.assertEqual(schedule[day], ["06:30", "08:30"])
        self.assertEqual(schedule[5], [])

    def test_weekday_range_expands_each_range_in_a_mixed_heading(self):
        html = """
        <table>
          <tr><th>Stop Name</th><th>Mon, Wed–Fri</th></tr>
          <tr><td>Navan</td><td>06:30</td></tr>
        </table>
        """
        schedule = PARSER.parse_weekday_departures(html, "Navan")
        self.assertIsNotNone(schedule)
        for day in (0, 2, 3, 4):
            self.assertEqual(schedule[day], ["06:30"])
        for day in (1, 5, 6):
            self.assertEqual(schedule[day], [])

    def test_weekday_range_accepts_through_word(self):
        html = """
        <table>
          <tr><th>Stop Name</th><th>Monday through Friday</th></tr>
          <tr><td>Navan</td><td>06:30</td></tr>
        </table>
        """
        schedule = PARSER.parse_weekday_departures(html, "Navan")
        self.assertIsNotNone(schedule)
        for day in range(5):
            self.assertEqual(schedule[day], ["06:30"])
        self.assertEqual(schedule[5], [])
        self.assertEqual(schedule[6], [])

    def test_overlapping_weekday_columns_without_journey_labels_are_ambiguous(self):
        html = """
        <table>
          <tr><th>Stop Name</th><th>Mon–Fri</th><th>Mon–Sun</th></tr>
          <tr><td>Navan</td><td>06:30</td><td>08:30</td></tr>
        </table>
        """
        with self.assertRaises(AmbiguousTimetableError):
            PARSER.parse_weekday_departures(html, "Navan")

    def test_weekday_schedule_maps_distinct_service_columns_by_day(self):
        html = """
        <table>
          <tr><th>Stop Name</th><th>Mon–Fri</th><th>Saturday–Sunday</th></tr>
          <tr><td>Navan</td><td>06:30</td><td>08:30</td></tr>
        </table>
        """
        schedule = PARSER.parse_weekday_departures(html, "Navan")
        self.assertIsNotNone(schedule)
        self.assertEqual(schedule[0], ["06:30"])
        self.assertEqual(schedule[5], ["08:30"])
        self.assertEqual(schedule[6], ["08:30"])
        # A weekday-aware schedule keeps each service column assigned to
        # its labelled days instead of flattening them into one daily list.
    def test_weekday_schedule_leaves_generic_times_table_unchanged(self):
        html = """
        <table><tr><th>Stop Name</th><th>Times</th></tr>
        <tr><td>Balbriggan Station</td><td>06:20 · 07:30 · 09:40</td></tr></table>
        """
        self.assertIsNone(PARSER.parse_weekday_departures(html, "Balbriggan Station"))

    def test_weekday_schedule_uses_direction_hint_to_select_section(self):
        html = """
        <h2>Outbound</h2>
        <table><tr><th>Stop</th><th>Mon–Fri</th></tr>
        <tr><td>Shared Stop</td><td>06:30</td></tr></table>
        <h2>Return</h2>
        <table><tr><th>Stop</th><th>Saturday</th></tr>
        <tr><td>Shared Stop</td><td>15:30</td></tr></table>
        """
        schedule = PARSER.parse_weekday_departures(html, "Shared Stop", "Outbound")
        self.assertEqual(schedule[0], ["06:30"])
        self.assertEqual(schedule[5], [])


    def test_public_holiday_column_is_extracted_separately(self):
        html = """
        <table>
          <tr><th>Stop Name</th><th>Mon–Fri</th><th>Mon–Sun &amp; Public Holidays</th></tr>
          <tr><td>Enfield</td><td>07:00</td><td>07:30 · 10:10 · 12:10</td></tr>
        </table>
        """
        self.assertEqual(
            parse_holiday_departures(
                html, "Enfield", "Mon–Sun & Public Holidays"
            ),
            ["07:30", "10:10", "12:10"],
        )

    def test_holiday_column_requires_explicit_holiday_label(self):
        with self.assertRaises(TimetableParseError):
            parse_holiday_departures(
                "<table><tr><th>Mon–Fri</th></tr><tr><td>07:00</td></tr></table>",
                "Enfield",
                "Mon–Fri",
            )

    def test_empty_holiday_cell_means_no_service_not_missing_stop(self):
        html = """
        <table><tr><th>Stop Name</th><th>Mon–Sun &amp; Public Holidays</th></tr>
        <tr><td>Enfield</td><td>—</td></tr></table>
        """
        self.assertEqual(
            parse_holiday_departures(
                html, "Enfield", "Mon–Sun & Public Holidays"
            ),
            [],
        )

    def test_missing_holiday_column_still_fails_safely(self):
        html = """
        <table><tr><th>Stop Name</th><th>Mon–Fri</th></tr>
        <tr><td>Enfield</td><td>07:00</td></tr></table>
        """
        with self.assertRaises(TimetableParseError):
            parse_holiday_departures(
                html, "Enfield", "Mon–Sun & Public Holidays"
            )


if __name__ == "__main__":
    unittest.main()
