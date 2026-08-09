# Miele Wine (consumer cloud) — Home Assistant

Control and monitor a **Miele wine conditioning unit** (KWTUS / K7000 "EasyControl"
cooling appliances) from Home Assistant — including the **presentation light**, which
Miele's *3rd-party developer API* refuses to switch (`HTTP 400`) for cooling appliances
([astrandb/miele#730](https://github.com/astrandb/miele/issues/730)).

This integration talks to the **consumer app's cloud API** (`rest-*.domestic.miele-iot.com`)
using the same OAuth login the Miele phone app uses — so it can drive endpoints the
official/developer integrations can't.

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=kristoffeys&repository=miele-wine-ha&category=integration)

## Entities

| Entity | What |
|---|---|
| `light.*_presentation_light` | Presentation light on/off (`/Cooling/PresentationLight`) |
| `switch.*` | Sabbath mode, child lock, active air filter (auto-created if the appliance reports them) |
| `sensor.*_zone_N_temperature` | Current temperature per cooling zone |
| `sensor.*_zone_N_target_temperature` | Target temperature per zone (diagnostic) |
| `sensor.*_humidity_level` | Humidity control level (low/medium/high — the API exposes no %) |
| `sensor.*_zone_N_light_intensity` | Presentation-light intensity level (0–7, diagnostic) |
| `binary_sensor.*_zone_N_door` | Door open/closed per zone |

## Install

### Via HACS (recommended)

Click the badge to add this repository to HACS on your instance:

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=kristoffeys&repository=miele-wine-ha&category=integration)

…then **Download**, restart Home Assistant, and set up the integration (below). Or add
it manually: HACS → ⋮ → **Custom repositories** → paste this repo's URL, category
**Integration**.

### Set up the integration

1. Settings → Devices & Services → **Add Integration** → *Miele Wine*.
2. Enter your account **country code** (e.g. `be`, `de`, `nl`, `gb`).
3. The flow shows a Miele login URL. Open it in a browser, sign in **with the same
   account your phone app uses**, and when the browser refuses to open the final
   `miele://oauth2-code/?code=…` link (expected!), **copy that whole `miele://…` URL
   and paste it back** into the form.
4. Done — your wine cabinet and its entities appear.

> The appliance must already be set up in the Miele app on the **owner** account.

## How it works / limitations

- **Auth:** consumer MAP OAuth 2.0 + PKCE; the token (scope `mcs`) is refreshed
  automatically and persisted in the config entry (survives restarts).
- **Polling:** state is polled (~60 s). The appliance's realtime channel is a
  WebSocket (`mcs2`) — a future enhancement could push state instantly.
- **Unofficial:** this uses Miele's private consumer API, not a supported developer
  API. It can break if Miele changes endpoints. Use on your own account/appliance.
- Reverse-engineered against a **KWTUS 7096 E**. Other cooling appliances that expose
  `/Cooling/…` should work; entities self-adjust to what the appliance reports.

## Disclaimer

Not affiliated with or endorsed by Miele. Provided as-is. You are responsible for
complying with Miele's terms for your account.
