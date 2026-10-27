"""HTML parsing helpers for Local Link timetable pages."""

from html.parser import HTMLParser
import re
import unicodedata

_TIME_RE = re.compile(r"([01]?\d|2[0-3]):([0-5]\d)")
_SERVICE_WORDS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun", "holiday", "daily")


class TimetableParseError(ValueError):
    """Raised when a matching stop row cannot be selected safely."""


class AmbiguousTimetableError(TimetableParseError):
    """Raised when a stop appears in multiple different timetable rows."""


def _normalise(value: str) -> str:
    """Normalise whitespace and case for stop-name comparisons."""
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _times(value: str) -> list[str]:
    """Extract valid clock times, including tightly concatenated values."""
    return [f"{int(hour):02d}:{minute}" for hour, minute in _TIME_RE.findall(value)]


class _TableRowParser(HTMLParser):
    """Collect row text, table cells, service headers, and section headings."""

    _HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[str] = []
        self.table_rows: list[dict] = []
        self._row_depth = 0
        self._parts: list[str] = []
        self._cells: list[str] = []
        self._cell_parts: list[str] = []
        self._cell_tag: str | None = None
        self._heading_tag: str | None = None
        self._heading_parts: list[str] = []
        self._current_heading = ""
        self._table_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attr_map = dict(attrs)
        if tag == "table":
            self._table_depth += 1
        if tag == "tr":
            if self._row_depth == 0:
                self._parts = []
                self._cells = []
            self._row_depth += 1
        if tag in {"td", "th"} and self._row_depth:
            self._cell_tag = tag
            self._cell_parts = []
            try:
                self._cell_colspan = max(1, int(attr_map.get("colspan") or 1))
            except ValueError:
                self._cell_colspan = 1
        if tag in self._HEADING_TAGS:
            self._heading_tag = tag
            self._heading_parts = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"td", "th"} and self._cell_tag == tag:
            value = " ".join(self._cell_parts).strip()
            self._cells.extend([value] * getattr(self, "_cell_colspan", 1))
            self._cell_tag = None
            self._cell_parts = []
        if tag == "tr" and self._row_depth:
            self._row_depth -= 1
            if self._row_depth == 0:
                row = " ".join(self._parts)
                self.rows.append(f"{self._current_heading} | {row}")
                if self._table_depth:
                    cells = list(self._cells)
                    normalized = [_normalise(cell) for cell in cells]
                    header = any(
                        any(word in cell for word in _SERVICE_WORDS)
                        for cell in normalized
                    )
                    self.table_rows.append({
                        "heading": self._current_heading,
                        "cells": cells,
                        "is_header": header,
                    })
        if tag == "table" and self._table_depth:
            self._table_depth -= 1
        if self._heading_tag == tag and tag in self._HEADING_TAGS:
            heading = " ".join(self._heading_parts).strip()
            if heading:
                self._current_heading = heading
            self._heading_tag = None
            self._heading_parts = []

    def handle_data(self, data: str) -> None:
        if self._row_depth and data.strip():
            self._parts.append(data.strip())
            if self._cell_tag:
                self._cell_parts.append(data.strip())
        if self._heading_tag and data.strip():
            self._heading_parts.append(data.strip())


def _column_index(rows: list[dict], service_column_hint: str) -> int | None:
    """Find the cell index for a service column using a timetable header."""
    hint = _normalise(service_column_hint)
    headers = [row["cells"] for row in rows if row["is_header"]]
    for cells in headers:
        for index, cell in enumerate(cells):
            if hint and hint in _normalise(cell):
                return index
    return None


def parse_departures(
    html: str,
    stop_name: str,
    direction_hint: str | None = None,
    service_column_hint: str | None = None,
) -> list[str]:
    """Extract a stop's departures, optionally selecting a service-day column.

    Service-column hints match timetable header text such as "Mon–Fri" or
    "Mon–Sun & Public Holidays". Without a hint, legacy combined-row parsing
    remains available for older layouts. Tightly concatenated times and
    middle-dot separators are supported.
    """
    if not stop_name.strip():
        raise TimetableParseError("A stop name is required.")

    parser = _TableRowParser()
    parser.feed(html)
    target = _normalise(stop_name)
    hint = _normalise(direction_hint or "")
    column_hint = (service_column_hint or "").strip()
    matches: list[list[str]] = []

    if column_hint:
        for table_row in parser.table_rows:
            cells = table_row["cells"]
            if table_row["is_header"]:
                continue
            row_text = " ".join([table_row["heading"], *cells])
            normalized_row = _normalise(row_text)
            if target not in normalized_row or (hint and hint not in normalized_row):
                continue
            # Locate the header from the same table section. Search backwards
            # for the most recent service header before this stop row.
            row_position = parser.table_rows.index(table_row)
            header_rows = [
                row for row in parser.table_rows[:row_position]
                if row["is_header"] and row["heading"] == table_row["heading"]
            ]
            if not header_rows:
                continue
            header = header_rows[-1]["cells"]
            index = next(
                (i for i, cell in enumerate(header) if _normalise(column_hint) in _normalise(cell)),
                None,
            )
            if index is None or index >= len(cells):
                continue
            times = _times(cells[index])
            if times:
                matches.append(times)
    else:
        for row in parser.rows:
            normalized_row = _normalise(row)
            if target not in normalized_row:
                continue
            if hint and hint not in normalized_row:
                continue
            times = _times(row)
            if times:
                matches.append(times)

    if not matches:
        extra = f", service column '{service_column_hint}'" if column_hint else ""
        if hint:
            raise TimetableParseError(
                f"No timetable row containing stop '{stop_name}', hint '{direction_hint}'{extra}, and departure times was found."
            )
        raise TimetableParseError(
            f"No timetable row containing stop '{stop_name}'{extra} and departure times was found."
        )

    unique_matches = {tuple(times) for times in matches}
    if len(unique_matches) > 1:
        raise AmbiguousTimetableError(
            f"Stop '{stop_name}' appears in multiple rows with different departure times. Add a direction/section hint that appears in the desired row."
        )

    return matches[0]
