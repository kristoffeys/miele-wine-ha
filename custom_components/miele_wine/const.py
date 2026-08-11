"""Constants for the Miele Wine (consumer cloud) integration."""

from __future__ import annotations

DOMAIN = "miele_wine"
PLATFORMS = ["climate", "light", "switch", "number", "sensor", "binary_sensor"]

# Toggleable /Cooling/{name} settings exposed as switches. on_value is written to turn
# ON, off_value to turn OFF (PUT /Cooling/{name} {"Value": N}); state is on when the
# read-back Value == on_value.
COOLING_SWITCHES = {
    # key: (friendly name, on_value, off_value)
    "Sabbath": ("Sabbath mode", 1, 2),
    "ChildProof": ("Child lock", 1, 2),
    "AirFilter": ("Active air filter", 1, 2),
}

# Config entry keys
CONF_TOKENS = "tokens"          # the full token dict (access/refresh/cc/client_id/region/...)
CONF_MAC = "mac"                # appliance fabNumber/mac
CONF_COUNTRY = "country"

DEFAULT_SCAN_INTERVAL = 60      # seconds; the cloud rate-limits and is flaky, keep sane

# Options (config entry options, not data — set via the options flow, never at setup).
# Existing entries have no options at all, so every read goes through
# entry.options.get(key, default) and no migration is needed.
CONF_SCAN_INTERVAL = "scan_interval"
CONF_ADAPTIVE = "adaptive"

MIN_SCAN_INTERVAL = 15          # below this the flaky cloud starts rate-limiting us
MAX_SCAN_INTERVAL = 900
DEFAULT_ADAPTIVE = True         # see polling.next_interval() for what "adaptive" does
