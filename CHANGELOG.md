# Changelog

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
