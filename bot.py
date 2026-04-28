import json
import os
import sys
import time
import requests
import websocket

from model_engine import ModelEngineV2

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

print("🔥 BOT STARTING", flush=True)
print("🌍 CITIES:", CITIES, flush=True)

if not API_KEY:
    print("❌ MINUTETEMP_API_KEY not set", flush=True)
    sys.exit(1)

engine = ModelEngineV2()


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
        print("❌ Ticket error:", repr(e), flush=True)
        return None

    print("📨 Ticket status:", res.status_code, flush=True)

    if res.status_code != 200:
        print(res.text, flush=True)
        return None

    data = res.json()
    return data.get("data", {}).get("ticket") or data.get("ticket")


# -------------------------
# MESSAGE HANDLER
# -------------------------
def handle_message(msg):
    msg_type = msg.get("type")
    print("📥 MSG:", msg_type, flush=True)

    # ---------------- OBSERVATIONS ----------------
    if msg_type == "observation":
        engine.process_observation(msg)

    # ---------------- FORECASTS ----------------
    elif msg_type in ["forecast_versions", "forecast_updated"]:
        engine.process_forecast(msg)

    # ---------------- ORACLE SCORES ----------------
    elif msg_type == "oracle_scores_updated":
        engine.process_oracle_scores(msg)

    # ---------------- WEATHER ----------------
    elif msg_type == "weather_event":
        engine.process_weather_event(msg)

    # ---------------- SUBSCRIBE ----------------
    elif msg_type == "subscribed":
        print("✅ SUBSCRIBED", msg.get("accepted"), flush=True)

    # ---------------- OTHER ----------------
    else:
        print("📩 UNKNOWN:", msg_type, flush=True)

    engine.tick()


# -------------------------
# WS CALLBACKS
# -------------------------
def on_message(ws, message):
    try:
        data = json.loads(message)
        handle_message(data)
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
# CONNECT
# -------------------------
def connect():
    ticket = get_ticket()
    if not ticket:
        print("❌ No ticket — exiting", flush=True)
        return

    ws = websocket.WebSocketApp(
        WS_URL,
        subprotocols=["bearer", ticket],
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )

    ws.run_forever(ping_interval=30, ping_timeout=10)


if __name__ == "__main__":
    print("🚀 ENTERING MAIN LOOP", flush=True)
    connect()
