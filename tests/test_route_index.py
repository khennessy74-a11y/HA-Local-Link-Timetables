"""Tests for discovery of official Local Link timetable links."""

import importlib.util
from pathlib import Path
import unittest

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "local_link_timetables"
    / "route_index.py"
)
SPEC = importlib.util.spec_from_file_location("local_link_route_index", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
parse_route_index = MODULE.parse_route_index


class RouteIndexTests(unittest.TestCase):
    def test_finds_known_route_url_shapes_and_deduplicates(self):
        html = """
        <a href="/tfi-route-188/">TFI Route 188</a>
        <a href="/route-mh-32/">Route MH32</a>
        <a href="https://locallinklmf.ie/route-lh-701/?source=index#times">LH701</a>
        <a href="/tfi-route-188/">Route 188 duplicate</a>
        """
        routes = parse_route_index(html)
        self.assertEqual(len(routes), 3)
        urls = {route["value"] for route in routes}
        self.assertIn("https://locallinklmf.ie/tfi-route-188/", urls)
        self.assertIn("https://locallinklmf.ie/route-mh-32/", urls)
        self.assertIn("https://locallinklmf.ie/route-lh-701/", urls)

    def test_rejects_external_and_non_route_links(self):
        html = """
        <a href="https://example.com/tfi-route-999/">Fake route</a>
        <a href="http://locallinklmf.ie/tfi-route-999/">Insecure route</a>
        <a href="/timetables/">Index</a>
        <a href="/contact/">Contact</a>
        """
        self.assertEqual(parse_route_index(html), [])

    def test_resolves_relative_links_and_uses_fallback_label(self):
        routes = parse_route_index('<a href="/tfi-route-189/"></a>')
        self.assertEqual(routes, [{
            "value": "https://locallinklmf.ie/tfi-route-189/",
            "label": "tfi-route-189",
        }])

    def test_malformed_port_does_not_crash_discovery(self):
        html = '<a href="https://locallinklmf.ie:abc/tfi-route-188/">Bad port</a>'
        self.assertEqual(parse_route_index(html), [])

    def test_keeps_official_host_subdomains_only(self):
        html = """
        <a href="https://www.locallinklmf.ie/tfi-route-188/">WWW</a>
        <a href="https://locallinklmf.ie.evil.test/tfi-route-189/">Fake</a>
        """
        routes = parse_route_index(html)
        self.assertEqual(len(routes), 1)
        self.assertTrue(routes[0]["value"].startswith("https://www.locallinklmf.ie/"))


if __name__ == "__main__":
    unittest.main()
