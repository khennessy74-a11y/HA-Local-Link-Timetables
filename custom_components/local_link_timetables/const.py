"""Constants for the Local Link Timetables integration."""

DOMAIN = "local_link_timetables"
PLATFORM = "sensor"

CONF_URL = "url"
CONF_STOP_NAME = "stop_name"
CONF_DIRECTION_HINT = "direction_hint"
CONF_SERVICE_DAYS = "service_days"
CONF_NAME = "name"

WEEKDAY_OPTIONS = [
    {"value": "0", "label": "Monday"},
    {"value": "1", "label": "Tuesday"},
    {"value": "2", "label": "Wednesday"},
    {"value": "3", "label": "Thursday"},
    {"value": "4", "label": "Friday"},
    {"value": "5", "label": "Saturday"},
    {"value": "6", "label": "Sunday"},
]
DEFAULT_SERVICE_DAYS = ["0", "1", "2", "3", "4", "5", "6"]

DEFAULT_NAME = "Local Link"
DEFAULT_SCAN_INTERVAL_MINUTES = 15
SCAN_INTERVAL_MINUTES = DEFAULT_SCAN_INTERVAL_MINUTES
