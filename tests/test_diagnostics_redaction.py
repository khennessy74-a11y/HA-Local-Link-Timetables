"""Regression tests for the diagnostics privacy boundary."""

import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "local_link_timetables"
PACKAGE = types.ModuleType("local_link_timetables")
PACKAGE.__path__ = [str(ROOT)]
sys.modules.setdefault("local_link_timetables", PACKAGE)

# Diagnostics imports Home Assistant at module load. Provide narrow test doubles
# so its own diagnostic function can be exercised without a full HA installation.
ha = types.ModuleType("homeassistant")
ha_components = types.ModuleType("homeassistant.components")
ha_diagnostics = types.ModuleType("homeassistant.components.diagnostics")
ha_config_entries = types.ModuleType("homeassistant.config_entries")
ha_core = types.ModuleType("homeassistant.core")


def async_redact_data(data, to_redact):
    """Mirror Home Assistant's recursive key-based redaction contract."""
    if isinstance(data, dict):
        return {
            key: "**REDACTED**" if key in to_redact else async_redact_data(value, to_redact)
            for key, value in data.items()
        }
    if isinstance(data, list):
        return [async_redact_data(value, to_redact) for value in data]
    return data


ha_diagnostics.async_redact_data = async_redact_data
ha_config_entries.ConfigEntry = type("ConfigEntry", (), {})
ha_core.HomeAssistant = type("HomeAssistant", (), {})
ha.components = ha_components
ha_components.diagnostics = ha_diagnostics

_saved_modules = {
    name: sys.modules.get(name)
    for name in (
        "homeassistant",
        "homeassistant.components",
        "homeassistant.components.diagnostics",
        "homeassistant.config_entries",
        "homeassistant.core",
    )
}
sys.modules.update(
    {
        "homeassistant": ha,
        "homeassistant.components": ha_components,
        "homeassistant.components.diagnostics": ha_diagnostics,
        "homeassistant.config_entries": ha_config_entries,
        "homeassistant.core": ha_core,
    }
)
SPEC = importlib.util.spec_from_file_location(
    "local_link_timetables.diagnostics", ROOT / "diagnostics.py"
)
assert SPEC is not None and SPEC.loader is not None
DIAGNOSTICS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DIAGNOSTICS)
for _name, _module in _saved_modules.items():
    if _module is None:
        sys.modules.pop(_name, None)
    else:
        sys.modules[_name] = _module


class FakeCoordinator:
    def __init__(self):
        self.last_update_success = False
        self.last_exception = ValueError(
            "request failed for https://locallinklmf.ie/tfi-route-188/"
        )
        self.data = {0: ["06:30", "08:00"]}
        self.holiday_dates = {"2026-12-25"}
        self.holiday_times = ["09:15"]


class FakeEntry:
    entry_id = "entry-1"

    def as_dict(self):
        return {
            "title": "Kentstown Church outbound",
            "data": {
                "url": "https://locallinklmf.ie/tfi-route-188/",
                "stop_name": "Kentstown Church",
                "direction_hint": "Outbound",
                "name": "Kentstown to Dublin",
                "holiday_calendar": "calendar.public_holidays",
                "service_days": ["0", "1"],
            },
            "options": {},
        }


class DiagnosticsRedactionTests(unittest.TestCase):
    def test_diagnostics_redacts_sensitive_fields_and_exception_message(self):
        coordinator = FakeCoordinator()
        hass = types.SimpleNamespace(data={"local_link_timetables": {"entry-1": coordinator}})
        result = asyncio.run(
            DIAGNOSTICS.async_get_config_entry_diagnostics(hass, FakeEntry())
        )

        entry = result["entry"]
        self.assertEqual(entry["title"], "**REDACTED**")
        for key in ("url", "stop_name", "direction_hint", "name", "holiday_calendar"):
            self.assertEqual(entry["data"][key], "**REDACTED**")
        self.assertEqual(entry["data"]["service_days"], ["0", "1"])

        details = result["coordinator"]
        self.assertFalse(details["available"])
        self.assertEqual(details["last_exception_type"], "ValueError")
        self.assertNotIn("locallinklmf.ie", str(details))
        self.assertEqual(details["schedule"], {0: ["06:30", "08:00"]})
        self.assertEqual(details["holiday_dates"], ["2026-12-25"])
        self.assertEqual(details["holiday_times"], ["09:15"])

    def test_diagnostics_handles_missing_coordinator(self):
        hass = types.SimpleNamespace(data={})
        result = asyncio.run(
            DIAGNOSTICS.async_get_config_entry_diagnostics(hass, FakeEntry())
        )
        self.assertFalse(result["coordinator"]["available"])
        self.assertIsNone(result["coordinator"]["last_update_success"])
        self.assertIsNone(result["coordinator"]["last_exception_type"])
        self.assertIsNone(result["coordinator"]["schedule"])
        self.assertEqual(result["coordinator"]["holiday_dates"], [])
        self.assertEqual(result["coordinator"]["holiday_times"], [])


if __name__ == "__main__":
    unittest.main()
