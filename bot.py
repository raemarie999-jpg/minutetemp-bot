import json
import os
import sys
import requests
import websocket

from model_engine import ModelEngineV4

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
    print("❌ Missing API key", flush=True)
    sys.exit(1)

engine = ModelEngineV4()

# -------------------------
# GET TICKET
# -------------------------
def get_ticket():
    try:
        res = requests.post(
            TICKET_URL,
            headers={"X-API-Key": API_KEY},
            timeout=10,
        )
        data = res.json()
        return data.get("data", {}).get("ticket") or data.get("ticket")
    except Exception as e:
        print("❌ ticket error:", repr(e), flush=True)
        return None


# -------------------------
# MESSAGE ROUTER (CLEAN)
# -------------------------
def handle_message(msg):
    msg_type = msg.get("type")

    # OBSERVATIONS → ENGINE ONLY
    if msg_type == "observation":
        engine.process_observation(msg)
        return

    # ORACLE SCORES → CORE INTELLIGENCE
    elif msg_type == "oracle_scores_updated":
        engine.process_oracle_scores(msg)
        return

    # FORECAST DATA → OPTIONAL SIGNALS
    elif msg_type in ("forecast_versions", "forecast_updated"):
        engine.process_forecast(msg)
        return

    # WEATHER EVENTS → CONTEXT SIGNALS
    elif msg_type == "weather_event":
        engine.process_weather_event(msg)
        return

    # CONNECTION STATE
    elif msg_type == "subscribed":
        print("✅ STREAM CONNECTED", msg.get("accepted"), flush=True)
        return

    elif msg_type == "snapshot_complete":
        print("📦 SNAPSHOT COMPLETE", flush=True)
        return

    # EVERYTHING ELSE = IGNORE CLEANLY
    else:
        return


# -------------------------
# WEBSOCKET CALLBACKS
# -------------------------
def on_message(ws, message):
    try:
        handle_message(json.loads(message))
    except Exception as e:
        print("❌ parse error:", repr(e), flush=True)


def on_open(ws):
    print("🔌 CONNECTED", flush=True)

    for city in CITIES:
        ws.send(json.dumps({
            "type": "subscribe",
            "cities": [city]
        }))
        print(f"📡 subscribed: {city}", flush=True)


def on_error(ws, error):
    print("❌ ws error:", error, flush=True)


def on_close(ws, code, msg):
    print("🔌 disconnected", code, msg, flush=True)


# -------------------------
# CONNECT
# -------------------------
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
        on_error=on_error,
        on_close=on_close,
    )

    ws.run_forever(ping_interval=30, ping_timeout=10)


# -------------------------
# MAIN
# -------------------------
if __name__ == "__main__":
    print("🚀 RUNNING CLEAN ENGINE", flush=True)
    connect()
