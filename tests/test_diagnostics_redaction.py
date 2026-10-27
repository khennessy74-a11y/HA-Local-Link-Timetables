"""Regression tests for the diagnostics privacy boundary."""

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
# so the privacy field list can be tested without installing a full HA instance.
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


class DiagnosticsRedactionTests(unittest.TestCase):
    def test_redacts_stop_route_and_calendar_details_including_friendly_name(self):
        entry = {
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
        redacted = async_redact_data(entry, DIAGNOSTICS.TO_REDACT)
        self.assertEqual(redacted["data"]["url"], "**REDACTED**")
        self.assertEqual(redacted["data"]["stop_name"], "**REDACTED**")
        self.assertEqual(redacted["data"]["direction_hint"], "**REDACTED**")
        self.assertEqual(redacted["data"]["name"], "**REDACTED**")
        self.assertEqual(redacted["data"]["holiday_calendar"], "**REDACTED**")
        self.assertEqual(redacted["data"]["service_days"], ["0", "1"])
        self.assertEqual(redacted["title"], "Kentstown Church outbound")

    def test_sensitive_fields_are_in_the_redaction_contract(self):
        self.assertTrue(
            {
                "url",
                "stop_name",
                "direction_hint",
                "name",
                "holiday_calendar",
            }.issubset(DIAGNOSTICS.TO_REDACT)
        )


if __name__ == "__main__":
    unittest.main()
