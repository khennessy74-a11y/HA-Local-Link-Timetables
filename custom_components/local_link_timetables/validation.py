"""Pure validation helpers for Local Link timetable configuration."""

from urllib.parse import urlparse

from .const import (
    CONF_DIRECTION_HINT,
    CONF_HOLIDAY_CALENDAR,
    CONF_HOLIDAY_COLUMN,
    CONF_SERVICE_COLUMN,
    CONF_SERVICE_DAYS,
    CONF_STOP_NAME,
    CONF_URL,
)


def valid_timetable_url(url: str) -> bool:
    """Only allow HTTPS URLs on public Local Link timetable hosts."""
    if not isinstance(url, str) or not url or url != url.strip():
        return False
    try:
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower()
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and bool(parsed.netloc)
        and not parsed.netloc.endswith(":")
        and parsed.username is None
        and parsed.password is None
        and port in (None, 443)
        and (hostname == "locallinklmf.ie" or hostname.endswith(".locallinklmf.ie"))
    )


def entry_identity(data: dict) -> tuple[str, str, str, str]:
    """Return a normalized identity for duplicate detection across setup and edits."""
    def normalise(value: object) -> str:
        return " ".join(str(value or "").casefold().split())

    return (
        normalise(data.get(CONF_URL)).rstrip("/"),
        normalise(data.get(CONF_STOP_NAME)),
        normalise(data.get(CONF_DIRECTION_HINT)),
        normalise(data.get(CONF_SERVICE_COLUMN)),
    )


def validate_config_values(data: dict) -> str | None:
    """Validate form fields that do not require fetching a timetable page."""
    if not str(data.get(CONF_STOP_NAME, "")).strip():
        return "stop_name_required"

    service_days = data.get(CONF_SERVICE_DAYS)
    if not isinstance(service_days, (list, tuple, set)) or not service_days:
        return "service_days"
    if any(str(day) not in {"0", "1", "2", "3", "4", "5", "6"} for day in service_days):
        return "service_days"

    holiday_column = str(data.get(CONF_HOLIDAY_COLUMN, "")).strip()
    holiday_calendar = str(data.get(CONF_HOLIDAY_CALENDAR, "")).strip()
    if holiday_column and not str(data.get(CONF_SERVICE_COLUMN, "")).strip():
        return "holiday_service_column_required"
    if holiday_column and not holiday_calendar:
        return "holiday_calendar_required"
    if holiday_calendar and not holiday_column:
        return "holiday_column_required"
    return None
