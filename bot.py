import json
import os
import requests
import websocket

from model_engine import ModelEngine

API_KEY = os.getenv("MINUTETEMP_API_KEY")
WS_URL = "wss://api.minutetemp.com/ws/api/1m"
TICKET_URL = "https://api.minutetemp.com/api/v1/ws-ticket"

CITIES = ["nyc", "chi", "dal"]

engine = ModelEngine()

print("🔥 BOT STARTING")
print("🌍 CITIES:", CITIES)

# -------------------------
# MESSAGE ROUTER
# -------------------------
def handle_message(msg):
    msg_type = msg.get("type")
    print("📥 MSG:", msg_type, flush=True)

    try:
        if msg_type == "observation":
            engine.process_observation(msg)

        elif msg_type in ["forecast_updated", "forecast_versions"]:
            engine.process_forecast(msg)

        elif msg_type == "oracle_scores_updated":
            engine.process_scores(msg)

        elif msg_type == "weather_event":
            engine.process_weather_event(msg)

        elif msg_type == "snapshot_complete":
            print("📦 snapshot complete")

        elif msg_type == "subscribed":
            print("✅ subscribed:", msg.get("accepted"))

        else:
            print("📩 UNKNOWN:", msg_type)

        # 🔥 ALWAYS RUN REPORT LOOP
        engine.maybe_report()

    except Exception as e:
        print("❌ parse error:", repr(e), flush=True)


# -------------------------
# WS CALLBACKS
# -------------------------
def on_message(ws, message):
    handle_message(json.loads(message))


def on_open(ws):
    print("🔌 connected")
    for city in CITIES:
        ws.send(json.dumps({"type": "subscribe", "cities": [city]}))
        print("📡 subscribed:", city)


def get_ticket():
    res = requests.post(
        TICKET_URL,
        headers={"X-API-Key": API_KEY},
        timeout=10,
    )
    return res.json()["data"]["ticket"]


def connect():
    ticket = get_ticket()

    ws = websocket.WebSocketApp(
        WS_URL,
        subprotocols=["bearer", ticket],
        on_open=on_open,
        on_message=on_message,
    )

    ws.run_forever(ping_interval=30)


# -------------------------
# MAIN
# -------------------------
if __name__ == "__main__":
    print("🚀 RUNNING")
    connect()
