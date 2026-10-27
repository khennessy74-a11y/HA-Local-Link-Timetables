"""Pure validation helpers for Local Link timetable configuration."""

from urllib.parse import urlparse

from .const import CONF_DIRECTION_HINT, CONF_SERVICE_COLUMN, CONF_STOP_NAME, CONF_URL


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
