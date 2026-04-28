import json
import os
import sys
import requests
import websocket

from model_engine import ModelEngineV3

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

print("🔥 BOT STARTING", flush=True)
print("🌍 CITIES:", CITIES, flush=True)

if not API_KEY:
    print("❌ Missing API key", flush=True)
    sys.exit(1)

engine = ModelEngineV3()


# -------------------------
# TICKET
# -------------------------
def get_ticket():
    print("📡 Requesting ticket...", flush=True)

    try:
        res = requests.post(
            TICKET_URL,
            headers={"X-API-Key": API_KEY},
            timeout=10,
        )
    except Exception as e:
        print("❌ ticket error:", repr(e), flush=True)
        return None

    print("📨 Ticket status:", res.status_code, flush=True)

    if res.status_code != 200:
        print("❌ Failed ticket:", res.text, flush=True)
        return None

    data = res.json()
    return data.get("data", {}).get("ticket") or data.get("ticket")


# -------------------------
# MESSAGE ROUTER (CLEAN)
# -------------------------
def handle_message(msg):
    t = msg.get("type")
    print("📥 MSG:", t, flush=True)

    # ---------------- OBSERVATION ----------------
    if t == "observation":
        engine.process_observation(msg)

    # ---------------- FORECAST ----------------
    elif t in ("forecast_versions", "forecast_updated"):
        engine.process_forecast(msg)

    # ---------------- ORACLE SCORES ----------------
    elif t == "oracle_scores_updated":
        engine.process_oracle_scores(msg)

    # ---------------- WEATHER EVENTS ----------------
    elif t == "weather_event":
        engine.process_weather_event(msg)

    # ---------------- CONTROL ----------------
    elif t == "subscribed":
        print("✅ subscribed:", msg.get("accepted"), flush=True)

    elif t == "snapshot_complete":
        print("📦 snapshot complete", flush=True)

    # ---------------- UNKNOWN ----------------
    else:
        print("📩 UNKNOWN:", t, flush=True)

    # update dashboard every message (cheap + safe)
    engine.tick()


# -------------------------
# WEBSOCKET
# -------------------------
def on_message(ws, message):
    try:
        handle_message(json.loads(message))
    except Exception as e:
        print("❌ parse error:", repr(e), flush=True)


def on_open(ws):
    print("🔌 connected", flush=True)

    for city in CITIES:
        ws.send(json.dumps({
            "type": "subscribe",
            "cities": [city]
        }))
        print(f"📡 subscribed: {city}", flush=True)


def connect():
    ticket = get_ticket()
    if not ticket:
        print("❌ no ticket", flush=True)
        return

    ws = websocket.WebSocketApp(
        WS_URL,
        subprotocols=["bearer", ticket],
        on_open=on_open,
        on_message=on_message,
    )

    ws.run_forever(ping_interval=30, ping_timeout=10)


if __name__ == "__main__":
    print("🚀 RUNNING", flush=True)
    connect()
