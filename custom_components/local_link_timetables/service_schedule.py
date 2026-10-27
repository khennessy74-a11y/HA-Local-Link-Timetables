"""Service-day-aware departure calculations."""

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta


def next_departure(
    times: Sequence[str] | Mapping[int | str, Sequence[str]],
    now: datetime,
    service_days: list[str] | set[str] | tuple[str, ...],
    search_days: int = 14,
) -> tuple[str | None, int | None, str | None]:
    """Return next departure, minutes to it, and ISO service date.

    Times may be a legacy flat list or a mapping from weekday number
    (Monday=0) to that day's departures. This supports separate weekday,
    Saturday, and Sunday schedules. Public-holiday overrides are not inferred
    here; callers must identify holidays and provide the correct schedule.
    """
    if not times or not service_days:
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

    for offset in range(search_days + 1):
        service_date = (now + timedelta(days=offset)).date()
        weekday = service_date.weekday()
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
            return value, minutes_until, service_date.isoformat()

    return None, None, None
