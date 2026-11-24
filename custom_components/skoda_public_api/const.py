"""Constants for the Škoda (Public API) integration."""

DOMAIN = "skoda_public_api"

API_BASE_URL = "https://public.api.connect.skoda-auto.cz/api/v1"

CONF_VIN = "vin"
CONF_SCAN_INTERVAL = "scan_interval"  # minutes

# The public API allows 20 requests/hour per VIN (documented as "not final").
# 10 min = 6 req/h. Minimum 4 min = 15 req/h, leaving headroom for restarts.
DEFAULT_SCAN_INTERVAL = 10
MIN_SCAN_INTERVAL = 4
MAX_SCAN_INTERVAL = 1440

# Fallback wait (seconds) after HTTP 429 when the API sends no Retry-After.
DEFAULT_RETRY_AFTER = 900
MAX_RETRY_AFTER = 3600
