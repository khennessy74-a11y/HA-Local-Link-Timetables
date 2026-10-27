"""Regression tests for route and stop discovery helpers."""

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "local_link_timetables"


def load_module(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ROUTE_INDEX = load_module("route_index")
STOP_INDEX = load_module("stop_index")


class RouteIndexTests(unittest.TestCase):
    def test_route_index_resolves_deduplicates_and_sorts_official_links(self):
        html = """
        <a href="/tfi-route-195/">Route 195</a>
        <a href="https://locallinklmf.ie/tfi-route-188/?source=index">Route 188</a>
        <a href="/tfi-route-195/?duplicate=1">Route 195 duplicate</a>
        <a href="http://locallinklmf.ie/tfi-route-200/">Insecure</a>
        <a href="https://evil.example/tfi-route-201/">External</a>
        <a href="https://locallinklmf.ie.evil.example/tfi-route-202/">Lookalike</a>
        <a href="https://user@locallinklmf.ie/tfi-route-203/">Credential URL</a>
        <a href="https://locallinklmf.ie:8443/tfi-route-204/">Unexpected port</a>
        <a href="/timetables/">Index link</a>
        """
        self.assertEqual(
            ROUTE_INDEX.parse_route_index(html),
            [
                {"value": "https://locallinklmf.ie/tfi-route-188/", "label": "Route 188"},
                {"value": "https://locallinklmf.ie/tfi-route-195/", "label": "Route 195"},
            ],
        )

    def test_route_index_uses_url_as_fallback_for_empty_labels(self):
        routes = ROUTE_INDEX.parse_route_index('<a href="/tfi-route-192/"><span></span></a>')
        self.assertEqual(routes, [{"value": "https://locallinklmf.ie/tfi-route-192/", "label": "tfi-route-192"}])


class StopIndexTests(unittest.TestCase):
    def test_stop_discovery_handles_route_188_compact_times_and_stop_column(self):
        html = """
        <table>
          <tr><th>Departs</th><th>Stops</th><th>Stop Number</th><th>Restriction</th>
              <th colspan="2">Mon–Sat (1 journey)</th>
              <th colspan="6">Monday–Sunday (7 journeys)</th></tr>
          <tr><td>Navan</td><td>Kentstown Church</td><td>137851</td><td>P/S</td>
              <td>06:5708:23</td><td>—</td><td>11:26</td><td>13:26</td>
              <td>15:20</td><td>17:20</td><td>19:36</td><td>20:42</td></tr>
        </table>
        """
        self.assertEqual(
            STOP_INDEX.parse_stop_options(html),
            [{"value": "Kentstown Church", "label": "Kentstown Church"}],
        )

    def test_stop_discovery_deduplicates_names_and_ignores_headers(self):
        html = """
        <table><tr><th>Stop Name</th><th>Times</th></tr>
          <tr><td>Enfield</td><td>07:00 · 10:10</td></tr>
          <tr><td>Enfield</td><td>11:00</td></tr>
          <tr><td>Longwood</td><td>—</td></tr>
        </table>
        """
        self.assertEqual(
            STOP_INDEX.parse_stop_options(html),
            [{"value": "Enfield", "label": "Enfield"}],
        )

    def test_stop_discovery_handles_compact_times_without_invalid_hour_fragments(self):
        html = """
        <table><tr><th>Stop Name</th><th>Times</th></tr>
          <tr><td>Kells PCC</td><td>25:00 · 06:3007:45</td></tr>
        </table>
        """
        self.assertEqual(
            STOP_INDEX.parse_stop_options(html),
            [{"value": "Kells PCC", "label": "Kells PCC"}],
        )


if __name__ == "__main__":
    unittest.main()
