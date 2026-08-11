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

# Wine-safety thresholds. These come from GENERAL WINE-STORAGE GUIDANCE — a steady
# 10-14 °C cellar band, and the rule that sustained deviation rather than a momentary
# reading is what harms wine — and NOT from any Miele documentation: the appliance
# reports no such limits over this API. They are the defaults for the derived safety
# entities only; nothing here is written to the appliance.
SAFE_TEMP_LOW_C = 10.0
SAFE_TEMP_HIGH_C = 14.0
# A cabinet dips whenever the door opens, so an excursion has to persist to count.
EXCURSION_GRACE_SECONDS = 30 * 60
DOOR_OPEN_THRESHOLD_SECONDS = 60
# One hour of a one-minute poll is ~60 samples: enough to see a failing compressor's
# drift, short enough that a real change is not averaged away.
TREND_WINDOW_SECONDS = 60 * 60
