# Exploren API, reverse-engineered

Exploren's charger management is a white-labelled **AMPECO** platform. The app
is React Native (logic compiled to Hermes bytecode `index.android.bundle`).
All config comes from `au.com.exploren.cp.app.BuildConfig`:

| Key | Value |
|-----|-------|
| `APP_BACKEND_DOMAIN` | `exploren.au.charge.ampeco.tech` (REST API host) |
| `APP_BROADCAST_ENDPOINT` | `https://echo.au.charge.ampeco.tech` (Laravel Echo websocket, real-time only) |
| `APP_CLIENT_ID` | `1` (OAuth client id) |
| `TENANT` | `au-exploren` |
| `AUTH0_DOMAIN` | `""`, **empty, Auth0 bundled but unused**; auth is AMPECO-native |

Base URL: `https://exploren.au.charge.ampeco.tech/api/v1`
(the `/app/...` and `/api/v2/...` routes sit under the `/api/v1` prefix; the
host is a Laravel app, real-time updates go over Laravel Echo at the broadcast
endpoint.)

`APP_CLIENT_SECRET = URqvV7q90Tbi8SJrrhdhlH8aKScw0UugvnbuhyWW` (OAuth client
secret, extracted from BuildConfig; required for the password grant).

## Common headers

```
Accept: application/json
Content-Type: application/json
Accept-Language: en
X-App-Id: au.com.exploren.cp.app
X-App-Version: 2.171.0
Authorization: Bearer <access_token>      # on authenticated calls
```

## 1. Login, `POST /api/v1/app/oauth/token`

AMPECO/Laravel-Passport password grant. **Verified live**: with the correct
client secret a bad user returns "These credentials do not match our records."
(client auth passes), vs "Client authentication failed" without it.

```json
{
  "grant_type": "password",
  "client_id": "1",
  "client_secret": "URqvV7q90Tbi8SJrrhdhlH8aKScw0UugvnbuhyWW",
  "username": "<email>",
  "password": "<password>",
  "scope": "*"
}
```
→ `{ "token_type": "Bearer", "access_token": "...", "refresh_token": "...", "expires_in": ... }`

Refresh: same endpoint, `grant_type=refresh_token` + `refresh_token` + client id/secret.

## 2. Your own chargers, `GET /app/personal/charge-points`

Returns charge points you own, each with `evses[]` (`id`, `identifier`,
`status`, `isAvailable`, `connectors[]`, `maxPower`). The `evses[].id` is the
`evseId` used to start a session.

Related: `/app/home/charge-points`, `/app/personal/charge-points/evses/`,
`/app/personal/charge-point/{id}`.

## 3. Start charge ("Tap to confirm charge"), `POST /app/session/start`

```json
{ "evseId": <id>, "source": "App" }
```
Optional: `paymentMethodId`, `tariffId`, `autocharge`, `reservationId`, `amount`.

## 4. Session state

- `GET /app/session/active`, current active session(s)
- `GET /app/session/{id}`, a session
- `POST /app/session/{id}/stop`, stop charging

## 5. Vehicle state-of-charge (SoC)

Field: `carBatteryPercent`, returned at the top level of the
`GET /app/session/active` response (a sibling of `session`, not inside it).

**It is a live value, not a stored attribute.** It is populated from the
charger's OCPP SoC meter reports and pushed via the websocket event
`EVSEChargingPercentageChanged` (handler `onEVSEChargingPercentageChanged`,
rendered by `renderEvseBatteryPercent`). The REST field mirrors the last pushed
value. Consequently it is an **empty string** when:
  - the session is not actively charging (e.g. `chargingState: suspendedEVSE`,
    smart-charging holding current at 0), or
  - the charger/vehicle don't report SoC at all (ISO 15118 / OCPP SoC; many AC
    home chargers never send it).

So SoC is only meaningful while actively charging, and only on SoC-capable
hardware. Confirmed empty on a live `suspendedEVSE` session (evseStatus
`charging` but power ~0 due to a smart-charging schedule).

Real-time source: **Laravel Echo (Pusher protocol)** at `APP_BROADCAST_ENDPOINT`
(`https://echo.au.charge.ampeco.tech`), events `EVSEChargingPercentageChanged`
and `PersonalEVSEStatusChange` on a private channel (prefix `exploren`, keyed by
user/EVSE). Subscription authed against `POST /broadcasting/auth` with the
bearer token. The websocket delivers the same value push-style; it does not
exist for a vehicle that isn't in an active, SoC-reporting session.

## Notes

There are ~100 `/app/...` and `/api/v2/...` routes in the app (profile,
payment_methods, locations, reservation, subscriptions, vouchers, etc.); only
the ones needed to authenticate, enumerate chargers and drive a session are
documented here. This file is reference material for the Home Assistant
integration under `custom_components/exploren/`.
