"""Constants for the Miele Wine (consumer cloud) integration."""

from __future__ import annotations

DOMAIN = "miele_wine"
PLATFORMS = ["light", "switch", "number", "sensor", "binary_sensor"]

# The hardcoded COOLING_SWITCHES table used to live here. Switches are now derived
# from each node's own AllValues enumeration — see discovery.py, which also keeps the
# labels and the 1=on/2=off convention.

# Config entry keys
CONF_TOKENS = "tokens"          # the full token dict (access/refresh/cc/client_id/region/...)
CONF_MAC = "mac"                # appliance fabNumber/mac
CONF_COUNTRY = "country"

DEFAULT_SCAN_INTERVAL = 60      # seconds; the cloud rate-limits and is flaky, keep sane
