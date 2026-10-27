"""Tests for safe HTTP redirect handling without a Home Assistant runtime."""

import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "local_link_timetables"
PACKAGE = types.ModuleType("local_link_timetables")
PACKAGE.__path__ = [str(ROOT)]
sys.modules.setdefault("local_link_timetables", PACKAGE)
for module_name in ("const", "validation", "http"):
    spec = importlib.util.spec_from_file_location(
        f"local_link_timetables.{module_name}", ROOT / f"{module_name}.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
HTTP = sys.modules["local_link_timetables.http"]


class Response:
    def __init__(self, status=200, body="page", location=None):
        self.status = status
        self.body = body
        self.headers = {"Location": location} if location else {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")

    async def text(self):
        return self.body


class Session:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


class SafeRedirectTests(unittest.TestCase):
    def test_resolves_relative_and_official_redirects(self):
        base = "https://locallinklmf.ie/tfi-route-188/"
        self.assertEqual(
            HTTP.safe_redirect_url(base, "../tfi-route-189/"),
            "https://locallinklmf.ie/tfi-route-189/",
        )
        self.assertEqual(
            HTTP.safe_redirect_url(base, "https://www.locallinklmf.ie/tfi-route-188/"),
            "https://www.locallinklmf.ie/tfi-route-188/",
        )

    def test_rejects_external_downgrade_and_malformed_redirects(self):
        base = "https://locallinklmf.ie/tfi-route-188/"
        for location in (
            "https://evil.example/steal",
            "http://locallinklmf.ie/tfi-route-188/",
            "//127.0.0.1/admin",
            "https://locallinklmf.ie.evil.example/",
            "",
        ):
            with self.subTest(location=location):
                self.assertIsNone(HTTP.safe_redirect_url(base, location))

    def test_fetch_follows_only_approved_redirects(self):
        session = Session([
            Response(302, location="/tfi-route-189/"),
            Response(200, body="safe page"),
        ])
        result = asyncio.run(HTTP.fetch_public_page(
            session, "https://locallinklmf.ie/tfi-route-188/"
        ))
        self.assertEqual(result, "safe page")
        self.assertEqual(len(session.calls), 2)
        self.assertTrue(all(call[1]["allow_redirects"] is False for call in session.calls))

    def test_fetch_stops_before_requesting_external_redirect_target(self):
        session = Session([Response(302, location="https://evil.example/")])
        with self.assertRaisesRegex(ValueError, "unapproved URL"):
            asyncio.run(HTTP.fetch_public_page(
                session, "https://locallinklmf.ie/tfi-route-188/"
            ))
        self.assertEqual(len(session.calls), 1)

    def test_fetch_rejects_unapproved_initial_url(self):
        session = Session([])
        with self.assertRaisesRegex(ValueError, "Refusing to fetch"):
            asyncio.run(HTTP.fetch_public_page(session, "https://evil.example/"))
        self.assertEqual(session.calls, [])

    def test_fetch_caps_redirect_chain(self):
        session = Session([Response(302, location="/next/") for _ in range(6)])
        with self.assertRaisesRegex(ValueError, "Too many redirects"):
            asyncio.run(HTTP.fetch_public_page(
                session, "https://locallinklmf.ie/tfi-route-188/"
            ))
        self.assertEqual(len(session.calls), 6)


if __name__ == "__main__":
    unittest.main()
