"""HTTP helpers for fetching public Local Link timetable pages safely."""

from urllib.parse import urljoin

from .validation import valid_timetable_url

_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_MAX_REDIRECTS = 5


def safe_redirect_url(current_url: str, location: str) -> str | None:
    """Resolve a redirect only when it stays on an approved HTTPS timetable host."""
    if not isinstance(location, str) or not location.strip():
        return None
    target = urljoin(current_url, location.strip())
    return target if valid_timetable_url(target) else None


async def fetch_public_page(session, url: str, *, timeout: int = 20, headers=None) -> str:
    """Fetch a public timetable page without following redirects to arbitrary hosts."""
    if not valid_timetable_url(url):
        raise ValueError("Refusing to fetch a URL outside the approved Local Link hosts.")

    current_url = url
    for redirect_count in range(_MAX_REDIRECTS + 1):
        async with session.get(
            current_url,
            timeout=timeout,
            headers=headers,
            allow_redirects=False,
        ) as response:
            if response.status in _REDIRECT_STATUSES:
                if redirect_count == _MAX_REDIRECTS:
                    raise ValueError("Too many redirects while fetching timetable.")
                target = safe_redirect_url(
                    current_url, response.headers.get("Location", "")
                )
                if target is None:
                    raise ValueError("Timetable redirect points to an unapproved URL.")
                current_url = target
                continue
            response.raise_for_status()
            return await response.text()

    raise ValueError("Unable to retrieve timetable page.")
