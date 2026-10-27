"""Stop discovery helpers for published Local Link timetable pages."""

from html.parser import HTMLParser
import re
import unicodedata

_TIME_RE = re.compile(r"(?<!\d)(?:[01]?\d|2[0-3]):[0-5]\d(?!\d)")
_SKIP_LABELS = {
    "stop", "stop name", "stop location", "stop number", "stop no.",
    "times", "time", "depart", "departure", "return", "restriction",
}
_HEADER_LABELS = _SKIP_LABELS | {"departs", "stops", "stop no", "stop no"}
_PREFERRED_STOP_HEADERS = {"stops", "stop name", "stop"}


def _normalise(value: str) -> str:
    """Normalise cell text for robust header matching."""
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


class _StopTableParser(HTMLParser):
    """Extract table rows, including table identity and header rows."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[dict] = []
        self._in_row = False
        self._in_cell = False
        self._row: list[str] = []
        self._cell: list[str] = []
        self._cell_colspan = 1
        self._table_depth = 0
        self._table_serial = 0
        self._table_id = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        attr_map = dict(attrs)
        if tag == "table":
            self._table_depth += 1
            self._table_serial += 1
            self._table_id = self._table_serial
        elif tag == "tr":
            self._in_row = True
            self._row = []
        elif tag in {"td", "th"} and self._in_row:
            self._in_cell = True
            self._cell = []
            try:
                self._cell_colspan = max(1, int(attr_map.get("colspan") or 1))
            except ValueError:
                self._cell_colspan = 1

    def handle_data(self, data: str) -> None:
        if self._in_cell and data.strip():
            self._cell.append(data.strip())

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"td", "th"} and self._in_cell:
            value = " ".join(self._cell).strip()
            self._row.extend([value] * self._cell_colspan)
            self._cell = []
            self._in_cell = False
        elif tag == "tr" and self._in_row:
            if self._row:
                normalised = [_normalise(cell) for cell in self._row]
                is_header = any(cell in _HEADER_LABELS for cell in normalised)
                self.rows.append({
                    "cells": list(self._row),
                    "table_id": self._table_id if self._table_depth else 0,
                    "is_header": is_header,
                })
            self._row = []
            self._in_row = False
        elif tag == "table" and self._table_depth:
            self._table_depth -= 1


def _stop_name_from_row(cells: list[str], header: list[str] | None) -> str | None:
    """Prefer the column explicitly labelled as the stop, not the nearby town."""
    candidates = [
        cell.strip()
        for cell in cells
        if cell.strip()
        and not _TIME_RE.search(cell)
        and _normalise(cell) not in _SKIP_LABELS
        and not cell.strip().isdigit()
    ]
    if header:
        preferred = [
            index for index, label in enumerate(header)
            if _normalise(label) in _PREFERRED_STOP_HEADERS
        ]
        for index in preferred:
            if index < len(cells):
                value = cells[index].strip()
                if (
                    value
                    and not _TIME_RE.search(value)
                    and _normalise(value) not in _SKIP_LABELS
                    and not value.isdigit()
                ):
                    return " ".join(value.split())
    if not candidates:
        return None
    return " ".join(candidates[0].split())


def parse_stop_options(html: str) -> list[dict[str, str]]:
    """Return unique stop names from rows with times, using labelled stop columns."""
    parser = _StopTableParser()
    parser.feed(html)
    stops: dict[str, str] = {}
    for position, row in enumerate(parser.rows):
        cells = row["cells"]
        if row["is_header"] or not any(_TIME_RE.search(cell) for cell in cells):
            continue
        headers = [
            previous["cells"]
            for previous in parser.rows[:position]
            if previous["is_header"] and previous["table_id"] == row["table_id"]
        ]
        header = headers[-1] if headers else None
        name = _stop_name_from_row(cells, header)
        if not name or len(name) > 100:
            continue
        if name.casefold().startswith(("service ", "journey ")):
            continue
        stops.setdefault(_normalise(name), name)
    return [
        {"value": name, "label": name}
        for name in sorted(stops.values(), key=str.casefold)
    ]
