"""Local Link Timetables integration."""

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_DIRECTION_HINT,
    CONF_STOP_NAME,
    CONF_URL,
    DOMAIN,
    SCAN_INTERVAL_MINUTES,
)
from .parser import TimetableParseError, parse_departures

_LOGGER = logging.getLogger(__name__)


class LocalLinkCoordinator(DataUpdateCoordinator[list[str]]):
    """Fetch and parse departures for a configured stop."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.url = entry.data[CONF_URL]
        self.stop_name = entry.data[CONF_STOP_NAME]
        self.direction_hint = entry.data.get(CONF_DIRECTION_HINT, "")
        self.display_name = entry.data.get(CONF_NAME, self.stop_name)
        self.session = async_get_clientsession(hass)
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(minutes=SCAN_INTERVAL_MINUTES),
        )

    async def _async_update_data(self) -> list[str]:
        """Download the timetable and return times for the selected stop."""
        try:
            async with self.session.get(
                self.url,
                timeout=20,
                headers={"User-Agent": "HomeAssistant-LocalLinkTimetables/0.1"},
            ) as response:
                response.raise_for_status()
                html = await response.text()
            return parse_departures(html, self.stop_name, self.direction_hint)
        except TimetableParseError as err:
            raise UpdateFailed(str(err)) from err
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(f"Unable to retrieve Local Link timetable: {err}") from err


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
