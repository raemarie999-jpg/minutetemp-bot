import json
import os
import sys
import requests
import websocket

from model_engine import ModelEngineV4


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


def handle_message(msg):
    msg_type = msg.get("type")

    if msg_type == "observation":
        engine.process_observation(msg)

    elif msg_type == "oracle_scores_updated":
        engine.process_oracle_scores(msg)

    elif msg_type in ("forecast_updated", "forecast_versions"):
        engine.process_forecast(msg)

    elif msg_type == "weather_event":
        engine.process_weather_event(msg)

    elif msg_type == "subscribed":
        print("✅ connected", flush=True)

    elif msg_type == "snapshot_complete":
        print("📦 snapshot complete", flush=True)

    # ignore everything else cleanly
    return


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
