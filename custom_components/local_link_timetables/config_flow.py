"""Config flow for Local Link Timetables."""


import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_DIRECTION_HINT,
    CONF_HOLIDAY_CALENDAR,
    CONF_HOLIDAY_COLUMN,
    CONF_SERVICE_COLUMN,
    CONF_SERVICE_DAYS,
    CONF_STOP_NAME,
    CONF_URL,
    DEFAULT_NAME,
    DEFAULT_SERVICE_DAYS,
    DOMAIN,
    WEEKDAY_OPTIONS,
)
from .parser import AmbiguousTimetableError, TimetableParseError, parse_departures, parse_holiday_departures, parse_weekday_departures
from .route_index import INDEX_URL, parse_route_index
from .stop_index import parse_stop_options
from .validation import (
    entry_identity as _entry_identity,
    is_duplicate_entry,
    valid_timetable_url as _valid_timetable_url,
    validate_config_values,
)


def _config_schema(defaults: dict, route_options: list[dict[str, str]] | None = None) -> vol.Schema:
    """Build the route-selection or options form with existing values as defaults."""
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
        }
    )


def _details_schema(
    defaults: dict, stop_options: list[dict[str, str]] | None = None
) -> vol.Schema:
    """Build the stop and service settings form."""
    return vol.Schema(
        {
            vol.Required(CONF_STOP_NAME, default=defaults.get(CONF_STOP_NAME, "")): (
                selector.SelectSelector(
                    selector.SelectSelectorConfig(options=stop_options)
                )
                if stop_options
                else str
            ),
            vol.Optional(CONF_DIRECTION_HINT, default=defaults.get(CONF_DIRECTION_HINT, "")): str,
            vol.Optional(CONF_SERVICE_COLUMN, default=defaults.get(CONF_SERVICE_COLUMN, "")): str,
            vol.Optional(CONF_HOLIDAY_COLUMN, default=defaults.get(CONF_HOLIDAY_COLUMN, "")): str,
            vol.Optional(
            CONF_HOLIDAY_CALENDAR,
            default=defaults.get(CONF_HOLIDAY_CALENDAR, ""),
        ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="calendar")
            ),
            vol.Required(
                CONF_SERVICE_DAYS,
                default=defaults.get(CONF_SERVICE_DAYS, DEFAULT_SERVICE_DAYS),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(options=WEEKDAY_OPTIONS, multiple=True)
            ),
            vol.Optional(CONF_NAME, default=defaults.get(CONF_NAME, DEFAULT_NAME)): str,
        }
    )


def _options_schema(defaults: dict) -> vol.Schema:
    """Build the editable options form; preserve manual URL and stop entry."""
    schema = {
        vol.Required(CONF_URL, default=defaults.get(CONF_URL, "https://locallinklmf.ie/tfi-route-188/")): str,
        vol.Required(CONF_STOP_NAME, default=defaults.get(CONF_STOP_NAME, "")): str,
        vol.Optional(CONF_DIRECTION_HINT, default=defaults.get(CONF_DIRECTION_HINT, "")): str,
        vol.Optional(CONF_SERVICE_COLUMN, default=defaults.get(CONF_SERVICE_COLUMN, "")): str,
        vol.Optional(CONF_HOLIDAY_COLUMN, default=defaults.get(CONF_HOLIDAY_COLUMN, "")): str,
        vol.Optional(
            CONF_HOLIDAY_CALENDAR,
            default=defaults.get(CONF_HOLIDAY_CALENDAR, ""),
        ): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="calendar")
        ),
        vol.Required(
            CONF_SERVICE_DAYS,
            default=defaults.get(CONF_SERVICE_DAYS, DEFAULT_SERVICE_DAYS),
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(options=WEEKDAY_OPTIONS, multiple=True)
        ),
        vol.Optional(CONF_NAME, default=defaults.get(CONF_NAME, DEFAULT_NAME)): str,
    }
    return vol.Schema(schema)

def _clean_input(data: dict) -> dict:
    """Normalize form values before validating or saving them."""
    cleaned = dict(data)
    cleaned[CONF_URL] = str(data.get(CONF_URL, "")).strip()
    cleaned[CONF_STOP_NAME] = str(data.get(CONF_STOP_NAME, "")).strip()
    cleaned[CONF_DIRECTION_HINT] = str(data.get(CONF_DIRECTION_HINT, "")).strip()
    cleaned[CONF_SERVICE_COLUMN] = str(data.get(CONF_SERVICE_COLUMN, "")).strip()
    cleaned[CONF_HOLIDAY_COLUMN] = str(data.get(CONF_HOLIDAY_COLUMN, "")).strip()
    cleaned[CONF_HOLIDAY_CALENDAR] = str(data.get(CONF_HOLIDAY_CALENDAR, "")).strip()
    cleaned[CONF_NAME] = str(data.get(CONF_NAME, "")).strip() or cleaned[CONF_STOP_NAME]
    cleaned[CONF_SERVICE_DAYS] = data.get(CONF_SERVICE_DAYS, DEFAULT_SERVICE_DAYS)
    return cleaned


async def _fetch_page(hass: HomeAssistant, url: str) -> str:
    """Fetch a public Local Link page using Home Assistant's shared session."""
    session = async_get_clientsession(hass)
    async with session.get(url, timeout=20) as response:
        response.raise_for_status()
        return await response.text()


async def _validate_input(hass: HomeAssistant, data: dict) -> str | None:
    """Validate the URL, stop, and optional direction hint against the live page."""
    url = data[CONF_URL].strip()
    field_error = validate_config_values(data)
    if field_error:
        return field_error
    if not _valid_timetable_url(url):
        return "invalid_url"

    try:
        html = await _fetch_page(hass, url)
        weekday_schedule = None
        if not data.get(CONF_SERVICE_COLUMN, ""):
            weekday_schedule = parse_weekday_departures(
                html, data[CONF_STOP_NAME], data.get(CONF_DIRECTION_HINT, "")
            )
        # Weekday-aware parsing is the runtime path for labelled service
        # columns. Avoid rejecting a valid schedule by then running legacy
        # flat-row parsing, which can see those distinct columns as ambiguous.
        if weekday_schedule is None or data.get(CONF_SERVICE_COLUMN, ""):
            parse_departures(
                html,
                data[CONF_STOP_NAME],
                data.get(CONF_DIRECTION_HINT, ""),
                data.get(CONF_SERVICE_COLUMN, ""),
            )
        if data.get(CONF_HOLIDAY_COLUMN):
            parse_holiday_departures(
                html, data[CONF_STOP_NAME], data[CONF_HOLIDAY_COLUMN],
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
        """Select a route from the published index."""
        errors: dict[str, str] = {}
        route_options = None
        try:
            route_options = parse_route_index(await _fetch_page(self.hass, INDEX_URL))
            if not route_options:
                errors["base"] = "route_index_unavailable"
        except Exception:  # noqa: BLE001
            errors["base"] = "route_index_unavailable"

        if user_input is not None:
            url = str(user_input.get(CONF_URL, "")).strip()
            if not _valid_timetable_url(url):
                errors["base"] = "invalid_url"
            else:
                self._selected_url = url
                return await self.async_step_details()

        return self.async_show_form(
            step_id="user",
            data_schema=_config_schema({}, route_options),
            errors=errors,
            description_placeholders={"example": "https://locallinklmf.ie/tfi-route-188/"},
        )

    async def async_step_details(self, user_input: dict | None = None):
        """Discover stops for the chosen route, then validate and save."""
        errors: dict[str, str] = {}
        url = getattr(self, "_selected_url", "https://locallinklmf.ie/tfi-route-188/")
        stop_options = None
        try:
            stop_options = parse_stop_options(await _fetch_page(self.hass, url))
            if not stop_options:
                errors["base"] = "stop_list_unavailable"
        except Exception:  # noqa: BLE001
            errors["base"] = "stop_list_unavailable"

        if user_input is not None:
            data = _clean_input({**user_input, CONF_URL: url})
            error = await _validate_input(self.hass, data)
            if error is None:
                identity = _entry_identity(data)
                entries = self.hass.config_entries.async_entries(DOMAIN)
                if is_duplicate_entry(data, entries):
                    errors["base"] = "already_configured"
                else:
                    # Also catch entries created by older versions with a
                    # different unique-ID format.
                    await self.async_set_unique_id("|".join(identity))
                    self._abort_if_unique_id_configured()
                    name = data.get(CONF_NAME) or data[CONF_STOP_NAME]
                    return self.async_create_entry(
                        title=name,
                        data={
                            CONF_URL: url,
                            CONF_STOP_NAME: data[CONF_STOP_NAME],
                            CONF_DIRECTION_HINT: data[CONF_DIRECTION_HINT],
                            CONF_SERVICE_COLUMN: data[CONF_SERVICE_COLUMN],
                            CONF_HOLIDAY_COLUMN: data[CONF_HOLIDAY_COLUMN],
                            CONF_HOLIDAY_CALENDAR: data[CONF_HOLIDAY_CALENDAR],
                            CONF_SERVICE_DAYS: data[CONF_SERVICE_DAYS],
                            CONF_NAME: name,
                        },
                    )
            else:
                errors["base"] = error

        return self.async_show_form(
            step_id="details",
            data_schema=_details_schema({}, stop_options),
            errors=errors,
            description_placeholders={"url": url},
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
                entries = self.hass.config_entries.async_entries(DOMAIN)
                if is_duplicate_entry(
                    user_input, entries, exclude_entry_id=self.config_entry.entry_id
                ):
                    error = "already_configured"
                else:
                    return self.async_create_entry(title="", data=user_input)
            errors["base"] = error

        defaults = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="init",
            data_schema=_options_schema(defaults),
            errors=errors,
            description_placeholders={"example": "https://locallinklmf.ie/tfi-route-188/"},
        )
