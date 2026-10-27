"""HTML parsing helpers for Local Link timetable pages."""

from html.parser import HTMLParser
import re
import unicodedata

_TIME_RE = re.compile(r"([01]?\d|2[0-3]):([0-5]\d)")


class TimetableParseError(ValueError):
    """Raised when a matching stop row cannot be found."""


def _normalise(value: str) -> str:
    """Normalise whitespace and case for stop-name comparisons."""
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


class _TableRowParser(HTMLParser):
    """Collect text from each HTML table row, including nested cell content."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[str] = []
        self._row_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "tr":
            if self._row_depth == 0:
                self._parts = []
            self._row_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "tr" and self._row_depth:
            self._row_depth -= 1
            if self._row_depth == 0:
                self.rows.append(" ".join(self._parts))

    def handle_data(self, data: str) -> None:
        if self._row_depth and data.strip():
            self._parts.append(data.strip())


def parse_departures(html: str, stop_name: str) -> list[str]:
    """Extract sorted HH:MM values from the best matching timetable row.

    Stop matching is case-insensitive and ignores repeated whitespace. If the
    same stop appears in more than one row, prefer the row with most times.
    """
    if not stop_name.strip():
        raise TimetableParseError("A stop name is required.")

    parser = _TableRowParser()
    parser.feed(html)
    target = _normalise(stop_name)
    matches: list[tuple[int, list[str]]] = []

    for row in parser.rows:
        if target not in _normalise(row):
            continue
        times = [f"{int(hour):02d}:{minute}" for hour, minute in _TIME_RE.findall(row)]
        if times:
            matches.append((len(times), times))

    if not matches:
        raise TimetableParseError(
            f"No timetable row containing stop '{stop_name}' and departure times was found."
        )

    # Preserve the timetable's listed order; do not sort, as some pages can
    # list special or overnight services in a deliberate order.
    return max(matches, key=lambda item: item[0])[1]
