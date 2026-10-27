"""Service-day-aware departure calculations."""

from datetime import datetime, timedelta


def next_departure(
    times: list[str],
    now: datetime,
    service_days: list[str] | set[str] | tuple[str, ...],
    search_days: int = 14,
) -> tuple[str | None, int | None, str | None]:
    """Return the next departure time, minutes to it, and ISO service date.

    Weekdays use Python's convention: Monday=0 through Sunday=6. Times are
    considered only on configured service days; after the final departure,
    the search advances to the next configured service day rather than
    automatically assuming the route runs tomorrow.
    """
    if not times or not service_days:
        return None, None, None

    active_days = {int(day) for day in service_days}
    parsed_times = sorted(
        (int(value[:2]) * 60 + int(value[3:]), value) for value in times
    )
    if any(day < 0 or day > 6 for day in active_days):
        raise ValueError("Service days must be weekday numbers from 0 to 6.")

    for offset in range(search_days + 1):
        service_date = (now + timedelta(days=offset)).date()
        if service_date.weekday() not in active_days:
            continue
        current_minute = (
            now.hour * 60 + now.minute if offset == 0 else -1
        )
        for minute, value in parsed_times:
            if minute < current_minute:
                continue
            departure = datetime.combine(
                service_date, datetime.min.time()
            ) + timedelta(minutes=minute)
            if offset == 0:
                remaining_seconds = (departure - now).total_seconds()
                minutes_until = max(0, int((remaining_seconds + 59) // 60))
            else:
                minutes_until = int((departure - now).total_seconds() // 60)
            return value, minutes_until, service_date.isoformat()

    return None, None, None
