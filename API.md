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

Returns `{ "data": [ chargePoint ] }`. Each charge point has `evses[]`, and
**each EVSE embeds its active `session`** (if any) plus `id`, `identifier`,
`status`, `connectors[]`, `maxPower`, `tariff`. This single call is therefore
enough to render live session state, no separate session request is needed.

Two distinct ids matter:
- `evse.id`, internal EVSE id (e.g. `"3760"`); use it as the stable device key.
- `evse.identifier`, the public EVSE id (e.g. `"3692"`); this is what the API
  means by `evseId` (it equals `session.evseId`), and it's what you pass to
  start a session.

Related: `/app/home/charge-points`, `/app/personal/charge-points/evses/`,
`/app/personal/charge-point/{id}`.

## 3. Start charge ("Tap to confirm charge"), `POST /app/session/start`

```json
{ "evseId": <evse.identifier>, "source": "App" }
```
Note `evseId` is the EVSE **identifier** (`3692`), not the internal `id`
(`3760`). Optional: `paymentMethodId`, `tariffId`, `autocharge`,
`reservationId`, `amount`.

## 4. Session state

- `GET /app/session/active`, current active session(s)
- `GET /app/session/{id}`, a session
- `POST /app/session/{id}/stop`, stop charging

## 5. Vehicle state-of-charge (SoC)

Field: `carBatteryPercent`. **It is a live, websocket-delivered value, not a
stored REST attribute**; populated from the charger's OCPP SoC meter reports
and pushed via the `EVSEChargingPercentageChanged` event (rendered by
`renderEvseBatteryPercent`). Over REST the field is empty/absent unless a
session is **actively charging** AND the charger + vehicle actually report SoC
(ISO 15118 / OCPP). Many AC home chargers never send it. Confirmed empty on a
live charging session (`/app/session/active` returned `carBatteryPercent: ""`,
and it is absent from the embedded charge-points session).

The integration reads `carBatteryPercent` from the embedded session if present,
so it works for SoC-capable hardware, but expects `unknown` otherwise. Real
SoC needs the websocket (see below).

## 6. Real-time websocket (implemented; verified live)

Live updates come over **`laravel-echo-server` (socket.io v2 / Engine.IO v3)**,
NOT Pusher (the echo host is `x-powered-by: Express`; `GET /` returns `OK`;
`GET /socket.io/?EIO=3&transport=polling` returns a socket.io handshake).
`laravel-echo` uses its `SocketIoConnector`.

Flow (all verified against the live server):
1. Connect `wss://echo.au.charge.ampeco.tech/socket.io/?EIO=3&transport=websocket`.
   Server sends `0{...}` (open) then `40` (auto-connects the default namespace).
2. Subscribe:
   `42["subscribe",{"channel":"private-{channelPrefix}.user.{userId}","auth":{"headers":{"Authorization":"Bearer <token>","X-Endpoint":"<api-base-url>"}}}]`
   - `channelPrefix` from `GET /app/settings/global` -> `broadcast.channelPrefix`;
     `broadcast.url` is the echo host; user id from `GET /app/profile` -> `id`.
   - **`X-Endpoint` is the key** (= `BASE_URL`,
     `https://exploren.au.charge.ampeco.tech/api/v1`). The echo host is shared
     across AU tenants; `X-Endpoint` tells it which tenant backend to run its
     server-side `/broadcasting/auth` against. This value comes from the
     decompiled Echo config (`auth.headers = {Authorization, X-Endpoint}`), not
     guessable from strings.
3. Keepalive: Engine.IO ping/pong (`2`/`3`); the integration pings when idle and
   pongs server pings.
4. Events arrive as `42[eventName, channel, data]` (namespace `App.Events`):
   `SessionChanged`, `EVSEChargingPercentageChanged`, `PersonalEVSEStatusChange`,
   `PersonalChargePointStatusChange`, `UnlockConnectorStatusChanged`,
   `ReservationChanged`. The integration refreshes the coordinator on any event.

Auth verification: subscribing to your own channel returns no error; another
user's channel returns `subscription_error … 403` (authenticated but forbidden),
vs `401` when `X-Endpoint` is missing/wrong; the discriminator that confirmed
the mechanism.

Additive: on any failure the integration falls back to REST polling. Live status
(`subscribed` / `channel` / `events_received` / `last_error`) is in the entry's
downloadable diagnostics.

## Notes

There are ~100 `/app/...` and `/api/v2/...` routes in the app (profile,
payment_methods, locations, reservation, subscriptions, vouchers, etc.); only
the ones needed to authenticate, enumerate chargers and drive a session are
documented here. This file is reference material for the Home Assistant
integration under `custom_components/exploren/`.
