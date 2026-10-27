"""Diagnostics support for Local Link Timetables."""

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_DIRECTION_HINT,
    CONF_HOLIDAY_CALENDAR,
    CONF_NAME,
    CONF_STOP_NAME,
    CONF_URL,
    DOMAIN,
)

# Redact both underlying values and labels that can repeat stop details.
TO_REDACT = {
    CONF_DIRECTION_HINT,
    CONF_HOLIDAY_CALENDAR,
    CONF_NAME,
    CONF_STOP_NAME,
    CONF_URL,
    "title",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict:
    """Return useful troubleshooting data without exposing route or stop details."""
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    last_exception = coordinator.last_exception if coordinator is not None else None
    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "coordinator": {
            "available": bool(coordinator and coordinator.last_update_success),
            "last_update_success": (
                coordinator.last_update_success if coordinator is not None else None
            ),
            # Exception messages may contain request URLs; expose only the type.
            "last_exception_type": (
                type(last_exception).__name__ if last_exception is not None else None
            ),
            "schedule": coordinator.data if coordinator is not None else None,
            "holiday_dates": (
                sorted(coordinator.holiday_dates) if coordinator is not None else []
            ),
            "holiday_times": (
                coordinator.holiday_times if coordinator is not None else []
            ),
        },
    }
