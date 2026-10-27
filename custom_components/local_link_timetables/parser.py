"""HTML parsing helpers for Local Link timetable pages."""

from html.parser import HTMLParser
import re
import unicodedata

_TIME_RE = re.compile(r"([01]?\d|2[0-3]):([0-5]\d)")


class TimetableParseError(ValueError):
    """Raised when a matching stop row cannot be selected safely."""


class AmbiguousTimetableError(TimetableParseError):
    """Raised when a stop appears in multiple different timetable rows."""


def _normalise(value: str) -> str:
    """Normalise whitespace and case for stop-name comparisons."""
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


class _TableRowParser(HTMLParser):
    """Collect table rows and the most recent heading for direction context."""

    _HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[str] = []
        self._row_depth = 0
        self._parts: list[str] = []
        self._heading_tag: str | None = None
        self._heading_parts: list[str] = []
        self._current_heading = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "tr":
            if self._row_depth == 0:
                self._parts = []
            self._row_depth += 1
        if tag in self._HEADING_TAGS:
            self._heading_tag = tag
            self._heading_parts = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "tr" and self._row_depth:
            self._row_depth -= 1
            if self._row_depth == 0:
                row = " ".join(self._parts)
                # Direction headings often sit outside the timetable table.
                self.rows.append(f"{self._current_heading} | {row}")
        if self._heading_tag == tag and tag in self._HEADING_TAGS:
            heading = " ".join(self._heading_parts).strip()
            if heading:
                self._current_heading = heading
            self._heading_tag = None
            self._heading_parts = []

    def handle_data(self, data: str) -> None:
        if self._row_depth and data.strip():
            self._parts.append(data.strip())
        if self._heading_tag and data.strip():
            self._heading_parts.append(data.strip())


def parse_departures(
    html: str, stop_name: str, direction_hint: str | None = None
) -> list[str]:
    """Extract times from a stop row and optionally disambiguate by direction.

    Supports tightly concatenated times (for example 06:5708:23) and pages
    using middle-dot separators. Direction hints can match row text or the
    most recent HTML heading above the row.
    """
    if not stop_name.strip():
        raise TimetableParseError("A stop name is required.")

    parser = _TableRowParser()
    parser.feed(html)
    target = _normalise(stop_name)
    hint = _normalise(direction_hint or "")
    matches: list[list[str]] = []

    for row in parser.rows:
        normalized_row = _normalise(row)
        if target not in normalized_row:
            continue
        if hint and hint not in normalized_row:
            continue
        times = [f"{int(hour):02d}:{minute}" for hour, minute in _TIME_RE.findall(row)]
        if times:
            matches.append(times)

    if not matches:
        if hint:
            raise TimetableParseError(
                f"No timetable row containing stop '{stop_name}', hint '{direction_hint}', and departure times was found."
            )
        raise TimetableParseError(
            f"No timetable row containing stop '{stop_name}' and departure times was found."
        )

    unique_matches = {tuple(times) for times in matches}
    if len(unique_matches) > 1:
        raise AmbiguousTimetableError(
            f"Stop '{stop_name}' appears in multiple rows with different departure times. Add a direction/section hint that appears in the desired row."
        )

    return matches[0]
