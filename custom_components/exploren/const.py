"""Constants for the Exploren integration."""

DOMAIN = "exploren"

# AMPECO backend for the Exploren tenant (from the app's BuildConfig).
BASE_URL = "https://exploren.au.charge.ampeco.tech/api/v1"
CLIENT_ID = "1"

# Real-time broadcast (laravel-echo-server / socket.io). Fallbacks; the live
# values come from /app/settings/global -> broadcast.{url,channelPrefix}.
BROADCAST_ENDPOINT = "https://echo.au.charge.ampeco.tech"
BROADCAST_CHANNEL_PREFIX = "exploren"
# Public app-embedded OAuth client secret shared by every install (from the APK
# BuildConfig). Not a private credential (the auth boundary is the user token);
# a fixed value the password grant requires, so it's a constant by design.
CLIENT_SECRET = "URqvV7q90Tbi8SJrrhdhlH8aKScw0UugvnbuhyWW"
APP_ID = "au.com.exploren.cp.app"
APP_VERSION = "2.171.0"

# Poll cadence for /app/personal/charge-points (one request per poll). Faster
# while a session is active, slower when idle, to stay well under the backend's
# rate limit. The app itself prefers a websocket for live updates and only polls
# as a fallback, so keep REST modest.
ACTIVE_SCAN_INTERVAL = 60
IDLE_SCAN_INTERVAL = 300

CONF_TOKEN = "token"
