#!/usr/bin/env python3
"""Standalone Exploren (AMPECO) API CLI for manual queries / debugging.

Independent of the Home Assistant integration: plain urllib, its own token
cache at ~/.exploren_token.json. Handy for poking the API by hand.

Credentials come from EXPLOREN_EMAIL / EXPLOREN_PASSWORD, read from the
environment or a `.env` file (current dir or next to this script). Real env
vars take precedence.

Usage:
  echo 'EXPLOREN_EMAIL=you@example.com\nEXPLOREN_PASSWORD=...' > .env
  python3 exploren.py login            # authenticate, cache token
  python3 exploren.py refresh          # force a token refresh
  python3 exploren.py chargers         # list your chargers + evse ids
  python3 exploren.py active           # current active session (404 = none)
  python3 exploren.py soc              # vehicle state-of-charge, if reported
  python3 exploren.py start <evseId>   # start charging ("Tap to confirm charge")
  python3 exploren.py stop <sessionId> # stop charging
  python3 exploren.py get <path>       # GET an arbitrary /app/... path

Only `login` needs credentials; other commands use the cached, auto-refreshed
token.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "https://exploren.au.charge.ampeco.tech/api/v1"
CLIENT_ID = "1"
# Public app-embedded OAuth client secret from the APK BuildConfig, shared by
# every install. Not a private credential (the auth boundary is the user token);
# it's a fixed value the password grant requires, so it's a constant by design.
CLIENT_SECRET = "URqvV7q90Tbi8SJrrhdhlH8aKScw0UugvnbuhyWW"
APP_ID = "au.com.exploren.cp.app"
APP_VERSION = "2.171.0"
TOKEN_FILE = Path.home() / ".exploren_token.json"


def load_dotenv():
    for path in (Path.cwd() / ".env", Path(__file__).resolve().parent / ".env"):
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[len("export "):]
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))
        return


def _base_headers():
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Accept-Language": "en",
        "X-App-Id": APP_ID,
        "X-App-Version": APP_VERSION,
        "User-Agent": f"Exploren/{APP_VERSION} (cli)",
    }


def _request(method, path, token=None, body=None):
    headers = _base_headers()
    if token:
        headers["Authorization"] = "Bearer " + token
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, raw


def save_token(tok):
    tok = dict(tok)
    if tok.get("expires_in") is not None:
        tok["expires_at"] = time.time() + float(tok["expires_in"])
    fd = os.open(TOKEN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(tok, f)
    os.chmod(TOKEN_FILE, 0o600)


def load_token_data():
    if not TOKEN_FILE.exists():
        sys.exit("No cached token. Run `login` first.")
    return json.loads(TOKEN_FILE.read_text())


def _oauth(payload):
    body = {**payload, "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET, "scope": "*"}
    status, data = _request("POST", "/app/oauth/token", body=body)
    if status == 200 and isinstance(data, dict) and data.get("access_token"):
        save_token(data)
        return data["access_token"]
    sys.exit(f"OAuth failed ({status}): {json.dumps(data)}")


def login():
    load_dotenv()
    email = os.environ.get("EXPLOREN_EMAIL")
    password = os.environ.get("EXPLOREN_PASSWORD")
    if not email or not password:
        sys.exit("Set EXPLOREN_EMAIL and EXPLOREN_PASSWORD (env or .env).")
    _oauth({"grant_type": "password", "username": email, "password": password})
    print(f"Logged in. Token cached at {TOKEN_FILE}")


def refresh():
    rtoken = load_token_data().get("refresh_token")
    if not rtoken:
        sys.exit("No refresh_token stored. Run `login` again.")
    _oauth({"grant_type": "refresh_token", "refresh_token": rtoken})
    print("Refreshed. New token cached.")


def valid_token():
    data = load_token_data()
    expires_at = data.get("expires_at")
    if not data.get("access_token") or (expires_at is not None and time.time() >= expires_at - 60):
        rtoken = data.get("refresh_token")
        if not rtoken:
            sys.exit("Token expired and no refresh_token. Run `login` again.")
        return _oauth({"grant_type": "refresh_token", "refresh_token": rtoken})
    return data["access_token"]


def authed_request(method, path, body=None):
    status, data = _request(method, path, token=valid_token(), body=body)
    if status == 401:
        rtoken = load_token_data().get("refresh_token")
        if rtoken:
            token = _oauth({"grant_type": "refresh_token", "refresh_token": rtoken})
            status, data = _request(method, path, token=token, body=body)
    return status, data


def _show(status, data):
    print(f"[{status}]")
    print(json.dumps(data, indent=2))


def _find_key(obj, key):
    if isinstance(obj, dict):
        if obj.get(key) is not None:
            return obj[key]
        for v in obj.values():
            found = _find_key(v, key)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = _find_key(v, key)
            if found is not None:
                return found
    return None


def chargers():
    _show(*authed_request("GET", "/app/personal/charge-points"))


def active():
    status, data = authed_request("GET", "/app/session/active")
    if status == 404:
        print("No active session.")
        return
    _show(status, data)


def soc():
    status, data = authed_request("GET", "/app/session/active")
    if status == 404:
        print("No active session, so no state-of-charge.")
        return
    if status != 200:
        _show(status, data)
        return
    pct = _find_key(data, "carBatteryPercent")
    state = _find_key(data, "chargingState") or _find_key(data, "evseStatus")
    if pct is None or pct == "":
        print(f"No SoC value (carBatteryPercent={pct!r}, chargingState={state!r}). "
              "Empty unless actively charging AND the charger/vehicle report SoC.")
    else:
        print(f"Vehicle battery: {pct}%  (chargingState={state})")


def start(evse_id):
    try:
        evse = int(evse_id)
    except ValueError:
        sys.exit(f"evseId must be a number, got {evse_id!r}")
    _show(*authed_request("POST", "/app/session/start", body={"evseId": evse, "source": "App"}))


def stop(session_id):
    _show(*authed_request("POST", f"/app/session/{session_id}/stop"))


def get(path):
    _show(*authed_request("GET", path if path.startswith("/") else "/" + path))


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    cmd, args = sys.argv[1], sys.argv[2:]
    fns = {
        "login": login,
        "refresh": refresh,
        "chargers": chargers,
        "active": active,
        "soc": soc,
        "start": start,
        "stop": stop,
        "get": get,
    }
    fn = fns.get(cmd)
    if not fn:
        sys.exit(__doc__)
    n_params = fn.__code__.co_argcount
    if len(args) != n_params:
        sys.exit(f"`{cmd}` expects {n_params} argument(s), got {len(args)}")
    fn(*args)


if __name__ == "__main__":
    main()
