# Changelog

## 0.3.0

Six new capabilities and two auth fixes. Everything still goes through the one write path
that works on cooling appliances — `PUT /V2/Devices/{mac}/Cooling/{name}` — because every
other route (local `/State`, cloud `/State`, DOP2, and the 3rd-party API's own `light`
action) is firmware-gated on these units. No new write channel was added.

### Added

- **Climate entity per cooling zone** (#7). Target temperature is now `climate.*_zone_N`,
  with the appliance's own min/max/step, replacing `number.*_zone_N_target_temperature` so
  exactly one entity ever writes `/Cooling/{zone}/TargetTemp`. Costs no extra API calls —
  the values were already in every poll.
- **Switches derived from the appliance's own `AllValues`** (#8). Every `/Cooling/` node
  reports its legal values (`{"Value": 2, "AllValues": [1, 2]}`), so switch entities now
  follow the payload instead of a hardcoded three-name table. Any two-valued setting the
  appliance offers — and any other Miele cooling appliance — works without a code change.
  `TempUnit` and `PresentationType` are deliberately excluded: they are enumerations, not
  toggles, and a "Temperature unit: on" switch would also change the appliance's own front
  panel. Existing switch `unique_id`s are unchanged.
- **Services `miele_wine.set_cooling_value` and `miele_wine.set_zone_value`** (#9). Write
  any `/Cooling/{name}` or `/Cooling/{zone}/{name}` node from an automation or Developer
  Tools, and get the appliance's raw reply back as service response data — useful for
  probing nodes this integration does not model yet. Node names are validated as a
  path-traversal guard, not merely for tidiness.
- **Adaptive polling and a polling options flow** (#10). Configurable scan interval
  (15–900 s, default 60) plus adaptive polling (default on): polls fast for a minute after
  a write and while a door is open, and backs off exponentially to 10 minutes while the
  cloud is failing, so a flaky upstream is not hammered harder.
- **Wine-safety entities** (#11), per zone: temperature-excursion and door-left-open
  *problem* binary sensors, minutes-out-of-range-today, and a °C/h temperature-trend
  sensor. Derived from the `Temp` and `Door` values already polled — no extra API calls,
  nothing written to the appliance. Wine is harmed by sustained deviation rather than one
  momentary reading, so the excursion alert integrates time out of band and only trips past
  a grace period.
- **Full device identity from `/Ident/`** (#6). Model, serial, firmware and XKM hardware
  version now populate the device page. The firmware string is what determines whether a
  given write is gated at all, so bug reports now carry it by default.

### Fixed

- Token refresh is serialised with an `asyncio` lock (#4). Two concurrent refreshes could
  race and invalidate each other's refresh token, forcing a reauth.
- Reauth uses `ConfigFlow.async_update_reload_and_abort` (#5) instead of updating the
  entry, firing a detached reload task, and then aborting — which was racy.

### Upgrade notes

- **`number.*_zone_N_target_temperature` is gone**, replaced by `climate.*_zone_N`. The old
  entity is removed from the registry automatically on upgrade, so it will not linger as
  *unavailable* — but any automation calling `number.set_value` on it must be changed to
  `climate.set_temperature`.
- **New switches may appear** if your appliance reports two-valued `/Cooling/` settings that
  earlier versions ignored (for example `SuperCooling`). Existing switches keep their entity
  IDs and history.
- **The wine-safety band is fixed at 10–14 °C** (grace 30 min, door 60 s, trend window 1 h).
  These come from general wine-storage guidance, *not* from Miele documentation — the
  appliance reports no such limits over this API. If your cabinet is deliberately set
  outside that range, the excursion sensor will read *problem* until the band is made
  configurable.
- Safety entity resolution is the poll interval, so a door opened and closed between two
  polls is invisible.

## 0.2.2
- Config flow: country is now a dropdown (built from the known MAP client-id table,
  still allows a custom value) instead of free text.
- Add config-entry diagnostics: a redacted state dump (entry data, device ident,
  coordinator state) downloadable from the device page for bug reports.
- Add a small backoff (0.5s, 1s) between retries of the flaky upstream `HTTP 500`
  on GETs instead of retrying immediately.

## 0.2.1
- Add reauthentication flow (recover after the token can no longer be refreshed,
  e.g. after a Miele password change) instead of forcing a delete + re-add.
- Detect rejected writes: a `200 [{"Failure":…}]` response now raises instead of
  silently "succeeding".
- Raise minimum Home Assistant to 2024.4 (uses `ConfigFlowResult`).
- Add a unit-test suite (auth/PKCE + write-result checker) and CI.

## 0.2.0
- Settable controls (number entities): per-zone target temperature and
  presentation-light intensity, and unit-wide humidity level.

## 0.1.2
- Bundle the brand icon in the integration (`brand/`) per the HA 2026.3 brands API.

## 0.1.1
- Fix `ModuleNotFoundError` on setup (import `DeviceInfo` from `homeassistant.helpers.entity`).

## 0.1.0
- Initial release: presentation light, sabbath/child-lock/air-filter switches,
  per-zone temperature + door, humidity level; consumer OAuth (PKCE) with token refresh.
