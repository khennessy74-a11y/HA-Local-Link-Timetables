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


def _contains_phrase(value: str, phrase: str) -> bool:
    """Match a phrase on word boundaries while tolerating HTML whitespace."""
    normalized_value = _normalise(value)
    normalized_phrase = _normalise(phrase)
    if not normalized_phrase:
        return True
    flexible_phrase = re.escape(normalized_phrase).replace(r"\ ", r"\s+")
    return re.search(rf"(?<!\w){flexible_phrase}(?!\w)", normalized_value) is not None


def _row_matches_stop(
    cells: list[str], stop_name: str, exact_only: bool = False
) -> bool:
    """Prefer exact stop cells whenever the page contains an exact match."""
    target = _normalise(stop_name)
    normalized_cells = [_normalise(cell) for cell in cells]
    if exact_only:
        return target in normalized_cells
    if target in normalized_cells:
        return True
    return any(_contains_phrase(cell, target) for cell in cells)


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
        self._heading_levels: dict[int, str] = {}
        self._table_depth = 0
        self._table_serial = 0
        self._current_table_id = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attr_map = dict(attrs)
        if tag == "table":
            self._table_depth += 1
            self._table_serial += 1
            self._current_table_id = self._table_serial
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
                    # A stop can legitimately contain a weekday word (for
                    # example, "Sunday Market"). Service headings are only
                    # header rows when the row itself contains no clock times.
                    has_times = any(_TIME_RE.search(cell) for cell in cells)
                    header = not has_times and any(
                        any(word in cell for word in _SERVICE_WORDS)
                        for cell in normalized
                    )
                    self.table_rows.append({
                        "heading": self._current_heading,
                        "heading_path": [
                            self._heading_levels[key]
                            for key in sorted(self._heading_levels)
                        ],
                        "table_id": self._current_table_id,
                        "cells": cells,
                        "is_header": header,
                    })
        if tag == "table" and self._table_depth:
            self._table_depth -= 1
        if self._heading_tag == tag and tag in self._HEADING_TAGS:
            heading = " ".join(self._heading_parts).strip()
            if heading:
                level = int(tag[1])
                self._heading_levels[level] = heading
                self._heading_levels = {
                    key: value for key, value in self._heading_levels.items()
                    if key <= level
                }
                self._current_heading = " | ".join(
                    self._heading_levels[key] for key in sorted(self._heading_levels)
                )
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
    matched_table_rows: list[tuple[int, list[str], list[str]]] = []
    exact_stop_exists = any(
        target in [_normalise(cell) for cell in row["cells"]]
        for row in parser.table_rows
    )

    if column_hint:
        for row_position, table_row in enumerate(parser.table_rows):
            cells = table_row["cells"]
            if table_row["is_header"]:
                continue
            row_text = " ".join([table_row["heading"], *cells])
            if not _row_matches_stop(cells, stop_name, exact_stop_exists):
                continue
            if hint and not _contains_phrase(row_text, direction_hint or ""):
                continue
            # Locate the header from the same table section. Search backwards
            # for the most recent service header before this stop row.
            header_rows = [
                row for row in parser.table_rows[:row_position]
                if row["is_header"]
                and row["table_id"] == table_row["table_id"]
                and row["heading"] == table_row["heading"]
            ]
            if not header_rows:
                continue
            header = header_rows[-1]["cells"]
            indices = [
                i for i, cell in enumerate(header)
                if _normalise(column_hint) in _normalise(cell)
            ]
            # Repeated header labels represent a grouped column (colspan), as
            # on Route 188 where "Mon–Sat" covers more than one journey.
            times = [
                departure
                for index in indices
                if index < len(cells)
                for departure in _times(cells[index])
            ]
            if times:
                matches.append(times)
    else:
        for table_row in parser.table_rows:
            cells = table_row["cells"]
            row_text = " ".join([table_row["heading"], *cells])
            if not _row_matches_stop(cells, stop_name, exact_stop_exists):
                continue
            if hint and not _contains_phrase(row_text, direction_hint or ""):
                continue
            times = _times(" ".join(cells))
            if times:
                matched_table_rows.append((
                    table_row["table_id"], times, table_row["heading_path"]
                ))

        if matched_table_rows:
            table_ids = [item[0] for item in matched_table_rows]
            if len(set(table_ids)) == len(table_ids):
                # Separate Service 1/2/3 tables under one direction heading
                # represent separate journeys and should be combined.
                paths = [item[2] for item in matched_table_rows]
                same_service_group = (
                    len(paths) > 1
                    and all(len(path) == len(paths[0]) for path in paths)
                    and all(path[:-1] == paths[0][:-1] for path in paths)
                    and all(
                        path[-1].casefold().startswith("service ")
                        for path in paths
                    )
                )
                if hint and same_service_group:
                    matches.append([
                        time for _table_id, times, _path in matched_table_rows
                        for time in times
                    ])
                else:
                    matches.extend(item[1] for item in matched_table_rows)
            else:
                matches.extend(item[1] for item in matched_table_rows)

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


_DAY_NAMES = {
    "mon": 0, "monday": 0, "tue": 1, "tues": 1, "tuesday": 1,
    "wed": 2, "wednesday": 2, "thu": 3, "thur": 3, "thurs": 3,
    "thursday": 3, "fri": 4, "friday": 4, "sat": 5, "saturday": 5,
    "sun": 6, "sunday": 6,
}


def _service_days_from_header(value: str) -> set[int]:
    """Return weekdays explicitly covered by a service-column heading."""
    text = _normalise(value).replace("–", "-").replace("—", "-")
    if "daily" in text:
        return set(range(7))
    tokens = re.findall(
        r"(?<!\w)(monday|mon|tuesday|tues|tue|wednesday|wed|thursday|thurs|thur|thu|friday|fri|saturday|sat|sunday|sun)(?!\w)",
        text,
    )
    days = [_DAY_NAMES[token] for token in tokens]
    if len(days) >= 2 and "-" in text:
        start, end = days[0], days[1]
        covered = set()
        day = start
        while True:
            covered.add(day)
            if day == end:
                break
            day = (day + 1) % 7
            if len(covered) == 7:
                break
        return covered
    return set(days)


def parse_weekday_departures(
    html: str,
    stop_name: str,
    direction_hint: str | None = None,
) -> dict[int, list[str]] | None:
    """Extract departures by weekday from explicitly labelled timetable columns.

    Columns applying to the same weekday are combined. This handles grouped
    layouts such as Route 188 where a Mon–Sat journey coexists with daily
    journeys. Returns None for generic tables without weekday headers, so
    callers can retain legacy flat-list parsing. Public holidays are not
    inferred from dates.
    """
    if not stop_name.strip():
        raise TimetableParseError("A stop name is required.")

    parser = _TableRowParser()
    parser.feed(html)
    target = _normalise(stop_name)
    hint = _normalise(direction_hint or "")
    exact_stop_exists = any(
        target in [_normalise(cell) for cell in row["cells"]]
        for row in parser.table_rows
    )
    candidates = []
    for position, row in enumerate(parser.table_rows):
        cells = row["cells"]
        if row["is_header"] or not _row_matches_stop(cells, stop_name, exact_stop_exists):
            continue
        row_text = " ".join([row["heading"], *cells])
        if hint and not _contains_phrase(row_text, direction_hint or ""):
            continue
        headers = [
            previous for previous in parser.table_rows[:position]
            if previous["is_header"]
            and previous["table_id"] == row["table_id"]
            and previous["heading"] == row["heading"]
        ]
        if not headers:
            continue
        header = headers[-1]["cells"]
        if any(_service_days_from_header(cell) for cell in header):
            candidates.append((row, header))

    if not candidates:
        return None
    if len(candidates) > 1:
        raise AmbiguousTimetableError(
            f"Stop '{stop_name}' appears in multiple weekday timetable rows. Add a direction/section hint."
        )

    row, header = candidates[0]

    # Two differently labelled service columns may be alternatives rather than
    # additive journeys. Only merge overlapping labels when the timetable
    # explicitly identifies them as journey groups (as Route 188 does).
    labelled = [
        (heading, _service_days_from_header(heading))
        for heading in header
        if _service_days_from_header(heading)
    ]
    for index, (left_label, left_days) in enumerate(labelled):
        for right_label, right_days in labelled[index + 1:]:
            if left_days & right_days and _normalise(left_label) != _normalise(right_label):
                journey_group = (
                    "journey" in _normalise(left_label)
                    and "journey" in _normalise(right_label)
                )
                if not journey_group:
                    raise AmbiguousTimetableError(
                        f"Stop '{stop_name}' has overlapping service columns "
                        f"'{left_label}' and '{right_label}'. Set the service-column "
                        "option to choose the intended timetable."
                    )

    schedule: dict[int, list[str]] = {day: [] for day in range(7)}
    for index, heading in enumerate(header):
        if index >= len(row["cells"]):
            continue
        days = _service_days_from_header(heading)
        if not days:
            continue
        for day in days:
            schedule[day].extend(_times(row["cells"][index]))

    for day, times in schedule.items():
        schedule[day] = sorted(
            set(times), key=lambda value: int(value[:2]) * 60 + int(value[3:])
        )
    return schedule



def parse_holiday_departures(
    html: str,
    stop_name: str,
    holiday_column_hint: str,
    direction_hint: str | None = None,
) -> list[str]:
    """Extract departures from one explicitly selected public-holiday column.

    The caller must configure the column separately from the ordinary schedule.
    This avoids guessing which overlapping service columns are alternatives.
    """
    hint = _normalise(holiday_column_hint)
    if not hint or "holiday" not in hint:
        raise TimetableParseError(
            "Choose a service-column heading that explicitly mentions public holidays."
        )
    parser = _TableRowParser()
    parser.feed(html)
    target = _normalise(stop_name)
    exact_stop_exists = any(
        target in [_normalise(cell) for cell in row["cells"]]
        for row in parser.table_rows
    )
    matches: list[list[str]] = []
    for position, row in enumerate(parser.table_rows):
        cells = row["cells"]
        if row["is_header"] or not _row_matches_stop(cells, stop_name, exact_stop_exists):
            continue
        row_text = " ".join([row["heading"], *cells])
        if direction_hint and not _contains_phrase(row_text, direction_hint):
            continue
        headers = [
            previous for previous in parser.table_rows[:position]
            if previous["is_header"]
            and previous["table_id"] == row["table_id"]
            and previous["heading"] == row["heading"]
        ]
        if not headers:
            continue
        header = headers[-1]["cells"]
        indices = [
            index for index, label in enumerate(header)
            if hint in _normalise(label) and "holiday" in _normalise(label)
        ]
        times = [
            value for index in indices if index < len(cells)
            for value in _times(cells[index])
        ]
        if times:
            matches.append(times)
    if not matches:
        raise TimetableParseError(
            f"No public-holiday departures found for stop '{stop_name}' in column '{holiday_column_hint}'."
        )
    unique = {tuple(values) for values in matches}
    if len(unique) > 1:
        raise AmbiguousTimetableError(
            f"Stop '{stop_name}' has multiple public-holiday timetable matches; add a direction/section hint."
        )
    return sorted(
        matches[0],
        key=lambda value: int(value[:2]) * 60 + int(value[3:]),
    )
