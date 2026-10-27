"""Local Link Timetables integration."""

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_DIRECTION_HINT,
    CONF_HOLIDAY_CALENDAR,
    CONF_HOLIDAY_COLUMN,
    CONF_SERVICE_COLUMN,
    CONF_STOP_NAME,
    CONF_URL,
    DOMAIN,
    SCAN_INTERVAL_MINUTES,
)
from .http import fetch_public_page
from .parser import TimetableParseError, parse_departures, parse_holiday_departures, parse_weekday_departures
from .service_schedule import holiday_dates_from_response, validate_holiday_calendar_response

_LOGGER = logging.getLogger(__name__)


class LocalLinkCoordinator(DataUpdateCoordinator[list[str] | dict[int, list[str]]]):
    """Fetch and parse departures for a configured stop."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.config = {**entry.data, **entry.options}
        self.url = self.config[CONF_URL]
        self.stop_name = self.config[CONF_STOP_NAME]
        self.direction_hint = self.config.get(CONF_DIRECTION_HINT, "")
        self.service_column = self.config.get(CONF_SERVICE_COLUMN, "")
        self.holiday_column = self.config.get(CONF_HOLIDAY_COLUMN, "")
        self.holiday_calendar = self.config.get(CONF_HOLIDAY_CALENDAR, "")
        self.holiday_dates: set[str] = set()
        self.holiday_times: list[str] = []
        self.display_name = self.config.get(CONF_NAME, self.stop_name)
        self.session = async_get_clientsession(hass)
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(minutes=SCAN_INTERVAL_MINUTES),
        )

    async def _async_update_data(self) -> list[str] | dict[int, list[str]]:
        """Download the timetable and return times for the selected stop."""
        try:
            html = await fetch_public_page(
                self.session,
                self.url,
                timeout=20,
                headers={"User-Agent": "HomeAssistant-LocalLinkTimetables/0.1"},
            )
            if self.holiday_column:
                self.holiday_times = parse_holiday_departures(
                    html, self.stop_name, self.holiday_column, self.direction_hint
                )
            else:
                self.holiday_times = []
            await self._async_update_holiday_dates()
            if not self.service_column:
                weekday_schedule = parse_weekday_departures(
                    html, self.stop_name, self.direction_hint
                )
                if weekday_schedule is not None:
                    return weekday_schedule
            return parse_departures(
                html, self.stop_name, self.direction_hint, self.service_column
            )
        except TimetableParseError as err:
            raise UpdateFailed(str(err)) from err
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(f"Unable to retrieve Local Link timetable: {err}") from err


    async def _async_update_holiday_dates(self) -> None:
        """Read events from the configured public-holiday calendar."""
        self.holiday_dates = set()
        if not self.holiday_calendar or not self.holiday_column:
            return
        start = dt_util.now()
        end = start + timedelta(days=15)
        try:
            response = await self.hass.services.async_call(
                "calendar",
                "get_events",
                {
                    "entity_id": self.holiday_calendar,
                    "start_date_time": start.isoformat(),
                    "end_date_time": end.isoformat(),
                },
                blocking=True,
                return_response=True,
            )
            validate_holiday_calendar_response(response, self.holiday_calendar)
            self.holiday_dates = holiday_dates_from_response(
                response, self.holiday_calendar
            )
        except Exception as err:  # noqa: BLE001
            # Fail closed: ordinary weekday times may be wrong on a public holiday.
            _LOGGER.warning(
                "Could not read configured holiday calendar %s; timetable will be unavailable until it recovers: %s",
                self.holiday_calendar,
                err,
            )
            raise RuntimeError(
                f"Could not read configured holiday calendar {self.holiday_calendar}"
            ) from err


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the integration."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a configured timetable."""
    coordinator = LocalLinkCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a configured timetable."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, ["sensor"]):
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
