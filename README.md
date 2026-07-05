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
before expiry and on a `401` (Laravel Passport rotates refresh tokens, so the
new pair is persisted each time).

**Your password is not stored**; only the email and the OAuth token bundle are
kept in the Home Assistant config entry. When the refresh token eventually
expires, Home Assistant raises a **reauthentication** prompt to re-enter your
password. You can also update your credentials any time via the integration's
**⋮ → Reconfigure** menu, no need to remove and re-add it.

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
all state comes from a single `/app/personal/charge-points` call (each connector
embeds its active `session`), and charging is driven via `/app/session/start`
and `/app/session/{id}/stop`. See [`API.md`](API.md) for the full
reverse-engineered API reference.

[`scripts/exploren.py`](scripts/exploren.py) is a standalone CLI (no HA needed)
for querying the API by hand, `login`, `chargers`, `active`, `soc`, `start`,
`stop`, `get <path>`. Useful for debugging; run `python3 scripts/exploren.py`
for usage.

## Configuration

| Setting  | Description                    |
|----------|--------------------------------|
| Email    | Your Exploren account email    |
| Password | Your Exploren account password |

Live updates come over the same **websocket** the app uses (`laravel-echo-server`
/ socket.io): the integration subscribes to your private channel and refreshes
instantly on session/charger events. REST polling is the fallback (60s active /
5min idle, one request per poll); if the websocket can't connect it degrades to
polling silently. Live status is in the entry's **Download diagnostics**
(`websocket` block). See [`API.md`](API.md) §6.
