"""Tests for discovering stop names from timetable rows."""

import importlib.util
from pathlib import Path
import unittest

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "local_link_timetables"
    / "stop_index.py"
)
SPEC = importlib.util.spec_from_file_location("local_link_stop_index", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
parse_stop_options = MODULE.parse_stop_options


class StopIndexTests(unittest.TestCase):
    def test_extracts_stops_only_from_rows_with_times(self):
        html = """
        <table>
          <tr><th>Stop Name</th><th>Stop Location</th><th>Times</th></tr>
          <tr><td>Kentstown Church</td><td>Kentstown</td><td>06:57 08:23</td></tr>
          <tr><td>Enfield</td><td>Main Street</td><td>07:00</td></tr>
          <tr><td>Not a departure row</td><td>Town</td><td>See note</td></tr>
        </table>
        """
        self.assertEqual(
            parse_stop_options(html),
            [
                {"value": "Enfield", "label": "Enfield"},
                {"value": "Kentstown Church", "label": "Kentstown Church"},
            ],
        )

    def test_deduplicates_case_insensitively_and_ignores_header_rows(self):
        html = """
        <table>
          <tr><th>Stop</th><th>Depart</th></tr>
          <tr><td>Ardee Bypass</td><td>07:40</td></tr>
          <tr><td>ardee bypass</td><td>11:30</td></tr>
          <tr><td>Service 1</td><td>13:30</td></tr>
          <tr><td>22</td><td>15:00</td></tr>
        </table>
        """
        self.assertEqual(
            parse_stop_options(html),
            [{"value": "Ardee Bypass", "label": "Ardee Bypass"}],
        )

    def test_empty_or_non_timetable_html_returns_empty_list(self):
        self.assertEqual(parse_stop_options("<p>No timetable available</p>"), [])


if __name__ == "__main__":
    unittest.main()
