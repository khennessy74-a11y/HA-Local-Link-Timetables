"""Discovery helpers for the Local Link timetable index."""

from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse, urlunparse

INDEX_URL = "https://locallinklmf.ie/timetables/"
_ALLOWED_HOST = "locallinklmf.ie"


def _normalise_url(href: str, base_url: str) -> str | None:
    """Resolve a link and reject anything outside the official timetable host."""
    candidate = urljoin(base_url, href.strip())
    parsed = urlparse(candidate)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not (
        hostname == _ALLOWED_HOST or hostname.endswith("." + _ALLOWED_HOST)
    ):
        return None
    path = parsed.path.rstrip("/") + "/"
    if path == "/timetables/" or not ("route" in path.casefold()):
        return None
    return urlunparse(("https", parsed.netloc.lower(), path, "", "", ""))


class _RouteLinkParser(HTMLParser):
    """Collect visible anchor labels and href values."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a":
            self._href = dict(attrs).get("href")
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._href is not None and data.strip():
            self._parts.append(data.strip())

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href is not None:
            self.links.append((self._href, " ".join(self._parts)))
            self._href = None
            self._parts = []


def parse_route_index(html: str, base_url: str = INDEX_URL) -> list[dict[str, str]]:
    """Return deduplicated official route links in stable display order."""
    parser = _RouteLinkParser()
    parser.feed(html)
    routes: dict[str, str] = {}
    for href, label in parser.links:
        url = _normalise_url(href, base_url)
        if not url:
            continue
        display = " ".join(label.split()) or url.rstrip("/").rsplit("/", 1)[-1]
        routes.setdefault(url, display)
    return [
        {"value": url, "label": label}
        for url, label in sorted(
            routes.items(), key=lambda item: (item[1].casefold(), item[0])
        )
    ]
