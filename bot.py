import json
import os
import time
import sys

import requests
import websocket

from model_engine import ModelEngine

# -------------------------
# CONFIG
# -------------------------
API_KEY = os.getenv("MINUTETEMP_API_KEY")

TICKET_URL = os.getenv(
    "MINUTETEMP_TICKET_URL",
    "https://api.minutetemp.com/api/v1/ws-ticket",
)
WS_URL = os.getenv(
    "MINUTETEMP_WS_URL",
    "wss://api.minutetemp.com/ws/api/1m",
)

CITIES = [
    c.strip()
    for c in os.getenv("CITIES", "nyc", "chi", "dal").split(",")
    if c.strip()
]

# Which prediction market we're tracking. Determines which station per city
# we accept observations/scores for. Options: kalshi, polymarket, robinhood,
# ibkr, all (no filter).
MARKET = os.getenv("MARKET", "kalshi").lower()

CITIES_CATALOG_URL = os.getenv(
    "MINUTETEMP_CITIES_URL",
    "https://api.minutetemp.com/api/v1/cities",
)

RECONNECT_DELAY = 5
MAX_RECONNECT_DELAY = 60

print("🔥 BOT STARTING", flush=True)
print("🌍 CITIES:", CITIES, flush=True)

if not API_KEY:
    print("❌ MINUTETEMP_API_KEY not set", flush=True)
    sys.exit(1)

engine = ModelEngine()

# Track which requested cities have been confirmed by the server.
_accepted_cities: set = set()
_subscribe_responses = 0
_subscribe_summary_printed = False

# city_slug -> set of station_ids we accept events from (based on MARKET).
ALLOWED_STATIONS: dict = {}


def _build_allowed_stations() -> dict:
    """Hit MinuteTemp's catalog and pick the station per city that the chosen
    prediction market actually settles against (e.g. Kalshi uses Central Park
    for NYC, not LaGuardia)."""
    if MARKET == "all":
        print("🎯 MARKET filter: all (no station filtering)", flush=True)
        return {}

    try:
        res = requests.get(
            CITIES_CATALOG_URL,
            headers={"X-API-Key": API_KEY},
            timeout=10,
        )
        res.raise_for_status()
        catalog = res.json().get("data", [])
    except Exception as e:
        print(
            f"⚠️ Could not fetch city catalog ({e!r}); accepting all stations",
            flush=True,
        )
        return {}

    flag = f"{MARKET}_active"
    allowed: dict = {}

    for city in catalog:
        slug = city.get("slug")
        if slug not in CITIES:
            continue
        stations = [
            s.get("station_id")
            for s in (city.get("stations") or [])
            if s.get(flag) and s.get("station_id")
        ]
        if stations:
            allowed[slug] = set(stations)

    print(f"🎯 MARKET filter: {MARKET}", flush=True)
    for slug in CITIES:
        sids = sorted(allowed.get(slug, set()))
        if sids:
            print(f"   {slug}: {sids}", flush=True)
        else:
            print(
                f"   {slug}: ⚠️ no {MARKET}_active station in catalog",
                flush=True,
            )
    return allowed


def _station_allowed(city: str, station_id) -> bool:
    """If we built a filter for this city, only accept matching stations."""
    if not ALLOWED_STATIONS:
        return True
    allowed = ALLOWED_STATIONS.get(city)
    if not allowed:
        # No filter for this city -> accept everything (fail open).
        return True
    return station_id in allowed


# -------------------------
# GET WEBSOCKET TICKET
# -------------------------
def get_ticket():
    print("📡 Requesting ticket...", flush=True)

    headers = {"X-API-Key": API_KEY}

    try:
        res = requests.post(TICKET_URL, headers=headers, timeout=10)
    except Exception as e:
        print("❌ Ticket request error:", repr(e), flush=True)
        return None

    print("📨 Ticket status:", res.status_code, flush=True)

    if res.status_code != 200:
        print("❌ Failed to get ticket", flush=True)
        print(res.text, flush=True)
        return None

    data = res.json()
    # Response shape: {"data": {"ticket": "..."}}
    inner = data.get("data") if isinstance(data, dict) else None
    if isinstance(inner, dict) and "ticket" in inner:
        return inner["ticket"]
    return data.get("ticket") if isinstance(data, dict) else None


# -------------------------
# EVENT ADAPTERS
# Convert MinuteTemp messages into ModelEngine events.
# -------------------------
def feed_observation(msg):
    city = msg.get("slug") or msg.get("city")
    station_id = msg.get("station_id")
    value = msg.get("temperature_f")
    if value is None:
        value = msg.get("value")

    if city is None or value is None:
        return

    if not _station_allowed(city, station_id):
        return

    engine.process_event({
        "type": "observation",
        "city": city,
        "station_id": station_id,
        "value": float(value),
    })


def feed_oracle_scores(msg):
    """oracle_scores_updated carries pre-computed 7-day rolling MAE/bias per
    model under one or more modes (e.g. `overall`, `day_ahead`). Forward each
    mode's scores to the engine so it can rank models by reliability."""
    city = msg.get("slug") or msg.get("city")
    if not city:
        return

    station_id = msg.get("station_id")
    if not _station_allowed(city, station_id):
        return

    modes = msg.get("modes") or ["overall"]

    for mode in modes:
        block = msg.get(mode)
        if not isinstance(block, dict):
            continue

        scores = block.get("scores")
        if not isinstance(scores, list):
            continue

        engine.process_event({
            "type": "oracle_scores",
            "city": city,
            "station_id": block.get("station_id") or station_id,
            "mode": mode,
            "scores": scores,
        })


# -------------------------
# MESSAGE HANDLER
# -------------------------
def handle_message(msg):
    msg_type = msg.get("type")

    if msg_type == "subscribed":
        global _subscribe_responses
        _subscribe_responses += 1
        accepted = msg.get("accepted") or {}
        accepted_cities = accepted.get("cities") or []
        if accepted_cities:
            for c in accepted_cities:
                _accepted_cities.add(c)
            print(f"✅ SUBSCRIBED → {accepted_cities}", flush=True)
        else:
            print("⚠️ SUBSCRIBE REJECTED (no cities accepted)", flush=True)
        _maybe_print_subscribe_summary()

    elif msg_type == "observation":
        slug = msg.get("slug")
        station_id = msg.get("station_id")
        keep = "✓" if _station_allowed(slug, station_id) else "✗"
        print(
            f"\n🌡 OBSERVATION {slug} | {station_id} {keep} | "
            f"{msg.get('temperature_f')}°F",
            flush=True,
        )
        feed_observation(msg)

    elif msg_type == "weather_event":
        print("\n⚠️ WEATHER EVENT", msg.get("summary"), flush=True)

    elif msg_type == "forecast_versions":
        # Carries only model-version timestamps, no prediction values.
        # We rely on `oracle_scores_updated` for the actual rankings.
        print(
            f"\n📊 FORECAST UPDATE {msg.get('slug')} {msg.get('station_id')}",
            flush=True,
        )

    elif msg_type == "oracle_scores_updated":
        print("\n📈 MODEL SCORES UPDATED", msg.get("slug"), flush=True)
        feed_oracle_scores(msg)

    else:
        print("\n📩 OTHER:", msg_type, flush=True)

    engine.maybe_send_daily_summary()


def _maybe_print_subscribe_summary():
    """Once we've received a `subscribed` reply for every subscribe call we
    sent, print a summary so any rejected cities are obvious."""
    global _subscribe_summary_printed
    if _subscribe_summary_printed:
        return
    if _subscribe_responses < len(CITIES):
        return
    _subscribe_summary_printed = True
    rejected = [c for c in CITIES if c not in _accepted_cities]
    if rejected:
        print(
            f"⚠️ Cities rejected by API (likely tier/access): {rejected}",
            flush=True,
        )
    print(f"✅ Streaming cities: {sorted(_accepted_cities)}", flush=True)


# -------------------------
# WEBSOCKET CALLBACKS
# -------------------------
def on_message(ws, message):
    try:
        data = json.loads(message)
        handle_message(data)
    except Exception as e:
        print("❌ Parse error:", repr(e), flush=True)


def on_open(ws):
    print("🔌 WebSocket connected", flush=True)
    # Subscribe per city so an unknown slug doesn't kill the whole batch.
    for city in CITIES:
        ws.send(json.dumps({"type": "subscribe", "cities": [city]}))
        print(f"📡 Subscribe sent: {city}", flush=True)


def on_error(ws, error):
    print("❌ WebSocket error:", error, flush=True)


def on_close(ws, close_status_code, close_msg):
    print("🔌 WebSocket closed", close_status_code, close_msg, flush=True)


# -------------------------
# MAIN LOOP (with reconnect)
# -------------------------
def run_once():
    ticket = get_ticket()
    if not ticket:
        return False

    print("🔌 Opening WebSocket...", flush=True)

    ws = websocket.WebSocketApp(
        WS_URL,
        subprotocols=["bearer", ticket],
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )
    ws.run_forever(ping_interval=30, ping_timeout=10)
    return True


def main():
    global ALLOWED_STATIONS
    ALLOWED_STATIONS = _build_allowed_stations()

    print("🚀 ENTERING MAIN LOOP", flush=True)
    delay = RECONNECT_DELAY
    while True:
        try:
            ok = run_once()
        except Exception as e:
            print("❌ Worker crashed:", repr(e), flush=True)
            ok = False

        wait = delay if ok else min(delay * 2, MAX_RECONNECT_DELAY)
        print(f"⏳ Reconnecting in {wait}s...", flush=True)
        time.sleep(wait)
        delay = wait if not ok else RECONNECT_DELAY


if __name__ == "__main__":
    main()
