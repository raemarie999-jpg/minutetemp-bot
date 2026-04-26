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
    for c in os.getenv("CITIES", "chi,nyc,dal").split(",")
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
# CACHE TICKET (IMPORTANT FIX)
# -------------------------
_cached_ticket = None


def get_ticket(force_refresh=False):
    global _cached_ticket

    if _cached_ticket and not force_refresh:
        return _cached_ticket

    print("📡 Requesting ticket...", flush=True)

    try:
        res = requests.post(
            TICKET_URL,
            headers={"X-API-Key": API_KEY},
            timeout=10,
        )
    except Exception as e:
        print("❌ Ticket request error:", repr(e), flush=True)
        return None

    print("📨 Ticket status:", res.status_code, flush=True)

    if res.status_code != 200:
        print("❌ Failed to get ticket", flush=True)
        print(res.text, flush=True)
        return None

    data = res.json()

    ticket = None
    if isinstance(data, dict):
        if "data" in data and isinstance(data["data"], dict):
            ticket = data["data"].get("ticket")
        else:
            ticket = data.get("ticket")

    if not ticket:
        print("❌ No ticket in response", flush=True)
        return None

    _cached_ticket = ticket
    return ticket


# -------------------------
# WEBSOCKET HANDLERS
# -------------------------
def handle_message(msg):
    msg_type = msg.get("type")

    if msg_type == "observation":
        print("\n🌡 OBSERVATION", msg.get("slug"), msg.get("temperature_f"), flush=True)

    elif msg_type == "subscribed":
        print("✅ SUBSCRIBED", msg.get("accepted"), flush=True)

    elif msg_type == "weather_event":
        print("\n⚠️ EVENT", msg.get("summary"), flush=True)

    else:
        print("\n📩 MSG:", msg_type, flush=True)


def on_message(ws, message):
    try:
        handle_message(json.loads(message))
    except Exception as e:
        print("❌ Parse error:", repr(e), flush=True)


def on_open(ws):
    print("🔌 WebSocket connected", flush=True)

    for city in CITIES:
        ws.send(json.dumps({
            "type": "subscribe",
            "cities": [city]
        }))
        print(f"📡 Subscribed: {city}", flush=True)


def on_error(ws, error):
    print("❌ WebSocket error:", error, flush=True)


def on_close(ws, code, msg):
    print("🔌 WebSocket closed", code, msg, flush=True)


# -------------------------
# MAIN LOOP
# -------------------------
def run_ws():
    ticket = get_ticket()
    if not ticket:
        return False

    print("🔌 Connecting WS...", flush=True)

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
            ok = run_ws()
        except Exception as e:
            print("❌ Crash:", repr(e), flush=True)
            ok = False

        # IMPORTANT: do NOT always refresh ticket
        if ok:
            delay = RECONNECT_DELAY
        else:
            delay = min(delay * 2, MAX_RECONNECT_DELAY)

        print(f"⏳ Restarting in {delay}s...", flush=True)
        time.sleep(delay)


if __name__ == "__main__":
    main()
