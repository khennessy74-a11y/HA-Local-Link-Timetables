"""Service-day-aware departure calculations."""

from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta


def validate_holiday_calendar_response(response: object, entity_id: str) -> None:
    """Reject malformed calendar responses instead of treating them as no holidays."""
    if not isinstance(response, Mapping):
        raise ValueError("Holiday calendar returned an invalid response.")
    calendar_data = response.get(entity_id)
    if not isinstance(calendar_data, Mapping):
        raise ValueError(f"Holiday calendar response did not include {entity_id}.")
    if not isinstance(calendar_data.get("events"), list):
        raise ValueError("Holiday calendar response did not contain an events list.")


def holiday_dates_from_response(response: object, entity_id: str) -> set[str]:
    """Extract valid ISO dates from a Home Assistant calendar service response."""
    if not isinstance(response, Mapping):
        return set()
    calendar_data = response.get(entity_id, {})
    if not isinstance(calendar_data, Mapping):
        return set()
    events = calendar_data.get("events", [])
    if not isinstance(events, list):
        return set()
    dates: set[str] = set()
    for event in events:
        if not isinstance(event, Mapping):
            continue
        value = str(event.get("start", ""))[:10]
        try:
            dates.add(date.fromisoformat(value).isoformat())
        except ValueError:
            continue
    return dates


def departures_for_date(
    times: Sequence[str] | Mapping[int | str, Sequence[str]],
    service_date: date,
    service_days: list[str] | set[str] | tuple[str, ...],
    holiday_dates: set[str] | frozenset[str] | None = None,
    holiday_times: Sequence[str] | None = None,
) -> list[str]:
    """Return the departures for one date, respecting holiday precedence.

    A configured holiday date always uses the holiday timetable, even when
    that timetable is empty. This prevents ordinary weekday times from being
    displayed as if they ran on a public holiday.
    """
    iso_date = service_date.isoformat()
    if iso_date in set(holiday_dates or ()):
        return sorted(
            list(holiday_times or ()),
            key=lambda value: int(value[:2]) * 60 + int(value[3:]),
        )

    active_days = {int(day) for day in service_days}
    if any(day < 0 or day > 6 for day in active_days):
        raise ValueError("Service days must be weekday numbers from 0 to 6.")
    weekday = service_date.weekday()
    if weekday not in active_days:
        return []
    if isinstance(times, Mapping):
        daily_times = list(times.get(weekday, times.get(str(weekday), ())))
    else:
        daily_times = list(times)
    return sorted(
        daily_times,
        key=lambda value: int(value[:2]) * 60 + int(value[3:]),
    )


def next_departure(
    times: Sequence[str] | Mapping[int | str, Sequence[str]],
    now: datetime,
    service_days: list[str] | set[str] | tuple[str, ...],
    search_days: int = 14,
    holiday_dates: set[str] | frozenset[str] | None = None,
    holiday_times: Sequence[str] | None = None,
) -> tuple[str | None, int | None, str | None]:
    """Return next departure, minutes to it, and ISO service date.

    Times may be a legacy flat list or a mapping from weekday number
    (Monday=0) to that day's departures. When a caller supplies explicit
    holiday dates and a holiday timetable, that timetable takes precedence
    on matching dates, including holidays that fall on weekdays. Calendar
    events are not inferred here; callers must pass dates from a dedicated
    public-holiday calendar.
    """
    if not times and not (holiday_dates and holiday_times):
        return None, None, None

    active_days = {int(day) for day in service_days}
    if any(day < 0 or day > 6 for day in active_days):
        raise ValueError("Service days must be weekday numbers from 0 to 6.")

    per_day: dict[int, list[str]] | None = None
    flat_times: list[str] = []
    if isinstance(times, Mapping):
        per_day = {}
        for day, values in times.items():
            weekday = int(day)
            if weekday < 0 or weekday > 6:
                raise ValueError("Schedule keys must be weekday numbers from 0 to 6.")
            per_day[weekday] = list(values)
    else:
        flat_times = list(times)

    holiday_set = set(holiday_dates or ())
    for offset in range(search_days + 1):
        service_date = (now + timedelta(days=offset)).date()
        iso_date = service_date.isoformat()
        is_holiday = iso_date in holiday_set
        weekday = service_date.weekday()
        if is_holiday:
            daily_times = list(holiday_times or ())
        else:
            if weekday not in active_days:
                continue
            daily_times = per_day.get(weekday, []) if per_day is not None else flat_times
        parsed_times = sorted(
            (int(value[:2]) * 60 + int(value[3:]), value)
            for value in daily_times
        )
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=offset)
        for minute, value in parsed_times:
            departure = midnight + timedelta(minutes=minute)
            if departure < now:
                continue
            remaining_seconds = (departure - now).total_seconds()
            minutes_until = max(0, int((remaining_seconds + 59) // 60))
            return value, minutes_until, iso_date

    return None, None, None
