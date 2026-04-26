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
    for c in os.getenv("CITIES", "nyc,chi,dal").split(",")
    if c.strip()
]

RECONNECT_DELAY = 5
MAX_RECONNECT_DELAY = 60

print("🔥 BOT STARTING", flush=True)
print("🌍 CITIES:", CITIES, flush=True)

if not API_KEY:
    print("❌ MINUTETEMP_API_KEY not set", flush=True)
    sys.exit(1)

engine = ModelEngine()


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
    value = msg.get("temperature_f")
    if value is None:
        value = msg.get("value")

    if city is None or value is None:
        return

    engine.process_event({
        "type": "observation",
        "city": city,
        "station_id": msg.get("station_id"),
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
        print("✅ SUBSCRIBED", flush=True)
        print("Accepted:", msg.get("accepted"), flush=True)

    elif msg_type == "observation":
        print(
            f"\n🌡 OBSERVATION {msg.get('slug')} | "
            f"{msg.get('station_id')} | {msg.get('temperature_f')}°F",
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
    ws.send(json.dumps({"type": "subscribe", "cities": CITIES}))
    print("📡 Subscribed to cities", flush=True)


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
