"""Stop discovery helpers for published Local Link timetable pages."""

from html.parser import HTMLParser
import re

_TIME_RE = re.compile(r"(?<!\d)(?:[01]?\d|2[0-3]):[0-5]\d(?!\d)")
_SKIP_LABELS = {"stop", "stop name", "stop location", "stop number", "stop no.", "times", "time", "depart", "departure", "return", "restriction"}


class _StopTableParser(HTMLParser):
    """Extract rows and their cell text without depending on a third-party parser."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._in_row = False
        self._in_cell = False
        self._row: list[str] = []
        self._cell: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag == "tr":
            self._in_row = True
            self._row = []
        elif tag in {"td", "th"} and self._in_row:
            self._in_cell = True
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._in_cell and data.strip():
            self._cell.append(data.strip())

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"td", "th"} and self._in_cell:
            self._row.append(" ".join(self._cell).strip())
            self._cell = []
            self._in_cell = False
        elif tag == "tr" and self._in_row:
            if self._row:
                self.rows.append(self._row)
            self._row = []
            self._in_row = False


def parse_stop_options(html: str) -> list[dict[str, str]]:
    """Return unique stop names from rows that contain at least one departure time.

    The first non-empty, non-time cell is treated as the stop name. Header rows,
    notes, and rows without a clock time are ignored. Results are sorted for a
    predictable selector, while the original stop spelling is preserved.
    """
    parser = _StopTableParser()
    parser.feed(html)
    stops: dict[str, str] = {}
    for cells in parser.rows:
        if not any(_TIME_RE.search(cell) for cell in cells):
            continue
        candidates = [
            cell.strip()
            for cell in cells
            if cell.strip()
            and not _TIME_RE.search(cell)
            and cell.strip().casefold() not in _SKIP_LABELS
            and not cell.strip().isdigit()
        ]
        if not candidates:
            continue
        name = candidates[0]
        # Ignore explanatory labels that can appear in non-stop rows.
        if len(name) > 100 or name.casefold().startswith(("service ", "journey ")):
            continue
        stops.setdefault(" ".join(name.split()).casefold(), " ".join(name.split()))
    return [
        {"value": name, "label": name}
        for name in sorted(stops.values(), key=str.casefold)
    ]
