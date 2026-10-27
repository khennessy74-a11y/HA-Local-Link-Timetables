"""Config flow for Local Link Timetables."""

from urllib.parse import urlparse

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_DIRECTION_HINT,
    CONF_STOP_NAME,
    CONF_URL,
    DEFAULT_NAME,
    DOMAIN,
)
from .parser import AmbiguousTimetableError, TimetableParseError, parse_departures


def _valid_timetable_url(url: str) -> bool:
    """Only allow public Local Link timetable hosts."""
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    return (
        parsed.scheme == "https"
        and (hostname == "locallinklmf.ie" or hostname.endswith(".locallinklmf.ie"))
    )


async def _validate_input(hass: HomeAssistant, data: dict) -> str | None:
    """Validate the URL, stop, and optional direction hint against the live page."""
    url = data[CONF_URL].strip()
    if not _valid_timetable_url(url):
        return "invalid_url"

    try:
        session = async_get_clientsession(hass)
        async with session.get(url, timeout=20) as response:
            response.raise_for_status()
            html = await response.text()
        parse_departures(
            html,
            data[CONF_STOP_NAME],
            data.get(CONF_DIRECTION_HINT, ""),
        )
    except AmbiguousTimetableError:
        return "ambiguous_stop"
    except TimetableParseError:
        return "stop_not_found"
    except Exception:  # noqa: BLE001
        return "cannot_connect"
    return None


class LocalLinkTimetablesConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle config flow for Local Link Timetables."""

    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None):
        """Configure a route page and stop."""
        errors: dict[str, str] = {}
        if user_input is not None:
            error = await _validate_input(self.hass, user_input)
            if error is None:
                url = user_input[CONF_URL].strip()
                stop_name = user_input[CONF_STOP_NAME].strip()
                direction_hint = user_input.get(CONF_DIRECTION_HINT, "").strip()
                await self.async_set_unique_id(
                    f"{url}|{stop_name.casefold()}|{direction_hint.casefold()}"
                )
                self._abort_if_unique_id_configured()
                name = user_input.get(CONF_NAME) or stop_name
                return self.async_create_entry(
                    title=name,
                    data={
                        CONF_URL: url,
                        CONF_STOP_NAME: stop_name,
                        CONF_DIRECTION_HINT: direction_hint,
                        CONF_NAME: name,
                    },
                )
            errors["base"] = error

        schema = vol.Schema(
            {
                vol.Required(CONF_URL, default="https://locallinklmf.ie/tfi-route-188/"): str,
                vol.Required(CONF_STOP_NAME): str,
                vol.Optional(CONF_DIRECTION_HINT, default=""): str,
                vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "example": "https://locallinklmf.ie/tfi-route-188/"
            },
        )
