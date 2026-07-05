# Exploren EV Charging. Home Assistant integration

Control and monitor a home EV charger managed by [Exploren](https://exploren.com.au)
(an [AMPECO](https://www.ampeco.com/)-based platform) from Home Assistant:
start/stop charging, and read live session data including vehicle state-of-charge
where the hardware reports it.

> Unofficial. Not affiliated with or endorsed by Exploren or AMPECO. It talks to
> the same private mobile-app API the Exploren app uses, with your own account.

## Features

- **Config flow**, sign in with your Exploren email + password (no YAML).
- **Start/stop charging**, **Start charging** and **Stop charging** `button`
  entities per connector (start = the app's "Tap to confirm charge").
- **Live session sensors**, energy (kWh), power (W), duration, cost, charging
  state, EVSE status, and **vehicle battery %** (`carBatteryPercent`).
- **Binary sensors**, charging, connected.
- One Home Assistant **device per connector (EVSE)**.

Tokens are handled automatically: the access token is refreshed proactively
before expiry and on a `401`, with a full re-login fallback (Laravel Passport
rotates refresh tokens, so the new pair is persisted each time).

## Installation (HACS)

1. HACS → ⋮ → **Custom repositories**.
2. Add this repository's URL, category **Integration**.
3. Install **Exploren EV Charging**, then restart Home Assistant.
4. **Settings → Devices & Services → Add Integration → Exploren**, and sign in.

Manual alternative: copy `custom_components/exploren/` into your HA
`config/custom_components/` directory and restart.

## Notes on vehicle state-of-charge

`Vehicle battery` (`carBatteryPercent`) is a **live** value pushed from the
charger's OCPP SoC reports, not a stored attribute. It is `unknown` unless the
session is **actively charging** *and* the charger + vehicle actually report SoC
(ISO 15118 / OCPP). Many AC home chargers never report it, in that case the
sensor stays `unknown` even mid-charge. This is a hardware limitation, not an
integration bug.

## How it works

Auth is AMPECO-native Laravel Passport (`/app/oauth/token` password grant);
data comes from `/app/personal/charge-points` and `/app/session/active`, and
charging is driven via `/app/session/start` and `/app/session/{id}/stop`. See
[`API.md`](API.md) for the full reverse-engineered API reference.

## Configuration

| Setting  | Description                    |
|----------|--------------------------------|
| Email    | Your Exploren account email    |
| Password | Your Exploren account password |

Polling interval is 30s.
