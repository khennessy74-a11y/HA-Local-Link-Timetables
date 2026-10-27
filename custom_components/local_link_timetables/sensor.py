"""Sensors for Local Link Timetables."""

from datetime import datetime, time, timedelta
import logging

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import CONF_SERVICE_DAYS, CONF_STOP_NAME, DEFAULT_SERVICE_DAYS, DOMAIN
from .service_schedule import next_departure
from .__init__ import LocalLinkCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    """Create the three entities for a configured stop."""
    coordinator: LocalLinkCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [
        LocalLinkNextDeparture(coordinator, entry),
        LocalLinkMinutesUntil(coordinator, entry),
        LocalLinkDepartures(coordinator, entry),
    ]
    async_add_entities(entities)

    @callback
    def refresh_time_based_entities(_now: datetime) -> None:
        """Update countdown sensors without fetching the website every minute."""
        for entity in entities:
            entity.async_write_ha_state()

    entry.async_on_unload(
        async_track_time_change(hass, refresh_time_based_entities, second=0)
    )


class LocalLinkBaseSensor(CoordinatorEntity[LocalLinkCoordinator], SensorEntity):
    """Base sensor with common timetable attributes."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: LocalLinkCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._config = {**entry.data, **entry.options}
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": self._config.get(CONF_NAME, self._config[CONF_STOP_NAME]),
            "manufacturer": "Local Link",
            "entry_type": "service",
        }

    @property
    def _times(self) -> list[str]:
        """Return the current list of departures."""
        return self.coordinator.data or []

    @property
    def _next_departure(self) -> tuple[str | None, int | None]:
        """Return the next departure on a configured service day."""
        departure, minutes, _service_date = next_departure(
            self._times,
            dt_util.now(),
            self._config.get(CONF_SERVICE_DAYS, DEFAULT_SERVICE_DAYS),
        )
        return departure, minutes

    @property
    def _next_service_date(self) -> str | None:
        """Return the date of the next departure, if one is scheduled."""
        return next_departure(
            self._times,
            dt_util.now(),
            self._config.get(CONF_SERVICE_DAYS, DEFAULT_SERVICE_DAYS),
        )[2]


class LocalLinkNextDeparture(LocalLinkBaseSensor):
    """Next departure time sensor."""

    _attr_icon = "mdi:bus-clock"

    def __init__(self, coordinator: LocalLinkCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_next_departure"
        self._attr_name = "Next departure"

    @property
    def native_value(self) -> str | None:
        """Return the next departure."""
        return self._next_departure[0]

    @property
    def extra_state_attributes(self) -> dict:
        """Expose source and full timetable."""
        return {
            "stop_name": self.coordinator.stop_name,
            "source_url": self.coordinator.url,
            "departures": self._times,
            "service_days": self._entry.data.get(CONF_SERVICE_DAYS, DEFAULT_SERVICE_DAYS),
            "next_service_date": self._next_service_date,
        }


class LocalLinkMinutesUntil(LocalLinkBaseSensor):
    """Minutes until the next listed departure."""

    _attr_icon = "mdi:timer-outline"
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: LocalLinkCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_minutes_until"
        self._attr_name = "Minutes until departure"

    @property
    def native_value(self) -> int | None:
        """Return minutes until the next departure."""
        return self._next_departure[1]

    @property
    def extra_state_attributes(self) -> dict:
        """Expose the associated departure time."""
        return {
            "stop_name": self.coordinator.stop_name,
            "next_departure": self._next_departure[0],
            "next_service_date": self._next_service_date,
        }


class LocalLinkDepartures(LocalLinkBaseSensor):
    """All departure times found for the selected stop."""

    _attr_icon = "mdi:format-list-bulleted"
    _attr_entity_category = None

    def __init__(self, coordinator: LocalLinkCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_departures"
        self._attr_name = "Departures"

    @property
    def native_value(self) -> str:
        """Return a compact list suitable for a sensor state."""
        return ", ".join(self._times) if self._times else "unknown"

    @property
    def extra_state_attributes(self) -> dict:
        """Expose departures as a structured list."""
        return {
            "stop_name": self.coordinator.stop_name,
            "source_url": self.coordinator.url,
            "departures": self._times,
            "service_days": self._entry.data.get(CONF_SERVICE_DAYS, DEFAULT_SERVICE_DAYS),
        }
