"""Config flow for Local Link Timetables."""

from urllib.parse import urlparse

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import selector

from .const import (
    CONF_DIRECTION_HINT,
    CONF_SERVICE_COLUMN,
    CONF_STOP_NAME,
    CONF_URL,
    CONF_SERVICE_DAYS,
    DEFAULT_NAME,
    DEFAULT_SERVICE_DAYS,
    DOMAIN,
    WEEKDAY_OPTIONS,
)
from .parser import AmbiguousTimetableError, TimetableParseError, parse_departures
from .route_index import INDEX_URL, parse_route_index


def _config_schema(defaults: dict, route_options: list[dict[str, str]] | None = None) -> vol.Schema:
    """Build the setup/options form using existing values as defaults."""
    return vol.Schema(
        {
            vol.Required(
                CONF_URL,
                default=defaults.get(CONF_URL, "https://locallinklmf.ie/tfi-route-188/"),
            ): (
                selector.SelectSelector(
                    selector.SelectSelectorConfig(options=route_options)
                )
                if route_options
                else str
            ),
            vol.Required(CONF_STOP_NAME, default=defaults.get(CONF_STOP_NAME, "")): str,
            vol.Optional(CONF_DIRECTION_HINT, default=defaults.get(CONF_DIRECTION_HINT, "")): str,
            vol.Optional(CONF_SERVICE_COLUMN, default=defaults.get(CONF_SERVICE_COLUMN, "")): str,
            vol.Required(
                CONF_SERVICE_DAYS,
                default=defaults.get(CONF_SERVICE_DAYS, DEFAULT_SERVICE_DAYS),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(options=WEEKDAY_OPTIONS, multiple=True)
            ),
            vol.Optional(CONF_NAME, default=defaults.get(CONF_NAME, DEFAULT_NAME)): str,
        }
    )


def _clean_input(data: dict) -> dict:
    """Normalize form values before validating or saving them."""
    cleaned = dict(data)
    cleaned[CONF_URL] = str(data.get(CONF_URL, "")).strip()
    cleaned[CONF_STOP_NAME] = str(data.get(CONF_STOP_NAME, "")).strip()
    cleaned[CONF_DIRECTION_HINT] = str(data.get(CONF_DIRECTION_HINT, "")).strip()
    cleaned[CONF_SERVICE_COLUMN] = str(data.get(CONF_SERVICE_COLUMN, "")).strip()
    cleaned[CONF_NAME] = str(data.get(CONF_NAME, "")).strip() or cleaned[CONF_STOP_NAME]
    cleaned[CONF_SERVICE_DAYS] = data.get(CONF_SERVICE_DAYS, DEFAULT_SERVICE_DAYS)
    return cleaned


def _entry_identity(data: dict) -> tuple[str, str, str, str]:
    """Return a normalized identity for duplicate detection across setup and edits."""
    return (
        data.get(CONF_URL, "").strip().rstrip("/").casefold(),
        " ".join(data.get(CONF_STOP_NAME, "").casefold().split()),
        " ".join(data.get(CONF_DIRECTION_HINT, "").casefold().split()),
        " ".join(data.get(CONF_SERVICE_COLUMN, "").casefold().split()),
    )


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
    if not data.get(CONF_STOP_NAME, "").strip():
        return "stop_name_required"
    if not data.get(CONF_SERVICE_DAYS, DEFAULT_SERVICE_DAYS):
        return "service_days"
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
            data.get(CONF_SERVICE_COLUMN, ""),
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
            user_input = _clean_input(user_input)
            error = await _validate_input(self.hass, user_input)
            if error is None:
                url = user_input[CONF_URL].strip()
                stop_name = user_input[CONF_STOP_NAME].strip()
                direction_hint = user_input.get(CONF_DIRECTION_HINT, "").strip()
                service_column = user_input.get(CONF_SERVICE_COLUMN, "").strip()
                await self.async_set_unique_id(
                    f"{url}|{stop_name.casefold()}|{direction_hint.casefold()}|{service_column.casefold()}"
                )
                self._abort_if_unique_id_configured()
                name = user_input.get(CONF_NAME) or stop_name
                return self.async_create_entry(
                    title=name,
                    data={
                        CONF_URL: url,
                        CONF_STOP_NAME: stop_name,
                        CONF_DIRECTION_HINT: direction_hint,
                        CONF_SERVICE_COLUMN: service_column,
                        CONF_SERVICE_DAYS: user_input.get(CONF_SERVICE_DAYS, DEFAULT_SERVICE_DAYS),
                        CONF_NAME: name,
                    },
                )
            errors["base"] = error

        route_options = None
        try:
            session = async_get_clientsession(self.hass)
            async with session.get(INDEX_URL, timeout=20) as response:
                response.raise_for_status()
                route_options = parse_route_index(await response.text())
            if not route_options:
                errors.setdefault("base", "route_index_unavailable")
        except Exception:  # noqa: BLE001
            # Keep manual URL entry available if the published index is unavailable.
            errors.setdefault("base", "route_index_unavailable")

        schema = _config_schema({}, route_options)
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "example": "https://locallinklmf.ie/tfi-route-188/"
            },
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        """Allow users to edit an existing timetable."""
        return LocalLinkTimetablesOptionsFlow(config_entry)


class LocalLinkTimetablesOptionsFlow(config_entries.OptionsFlow):
    """Edit the URL, stop, direction, service column, and service days."""

    def __init__(self, config_entry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict | None = None):
        """Validate and save changes to an existing timetable."""
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input = _clean_input(user_input)
            error = await _validate_input(self.hass, user_input)
            if error is None:
                identity = _entry_identity(user_input)
                duplicate = any(
                    entry.entry_id != self.config_entry.entry_id
                    and _entry_identity({**entry.data, **entry.options}) == identity
                    for entry in self.hass.config_entries.async_entries(DOMAIN)
                )
                if duplicate:
                    error = "already_configured"
                else:
                    return self.async_create_entry(title="", data=user_input)
            errors["base"] = error

        defaults = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="init",
            data_schema=_config_schema(defaults),
            errors=errors,
            description_placeholders={
                "example": "https://locallinklmf.ie/tfi-route-188/"
            },
        )
