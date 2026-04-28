import json
import os
import requests
import websocket

from model_engine import ModelEngine

API_KEY = os.getenv("MINUTETEMP_API_KEY")
TICKET_URL = "https://api.minutetemp.com/api/v1/ws-ticket"
WS_URL = "wss://api.minutetemp.com/ws/api/1m"

CITIES = [c.strip() for c in os.getenv("CITIES", "nyc").split(",")]

engine = ModelEngine()

# ✅ TELEGRAM CONFIG
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def send_telegram(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text},
            timeout=5
        )
    except Exception as e:
        print("⚠️ Telegram error:", repr(e), flush=True)


def handle_message(msg):
    msg_type = msg.get("type")

    if msg_type == "observation":
        engine.process_observation(msg)

    elif msg_type in ["forecast_updated", "forecast_versions"]:
        engine.process_forecast(msg)

    elif msg_type == "oracle_scores_updated":
        engine.process_scores(msg)

    elif msg_type == "weather_event":
        engine.process_weather_event(msg)

    elif msg_type == "snapshot_complete":
        print("📦 snapshot complete", flush=True)

    engine.maybe_report()

    # ✅ SEND LATEST REPORTS (SAFE + CONTROLLED)
    for city in engine.last_reports:
        send_telegram(engine.last_reports[city])


def on_message(ws, message):
    try:
        handle_message(json.loads(message))
    except Exception as e:
        print("❌ parse error:", repr(e), flush=True)


def on_open(ws):
    print("🔌 connected", flush=True)

    for city in CITIES:
        ws.send(json.dumps({"type": "subscribe", "cities": [city]}))
        print(f"📡 subscribed: {city}", flush=True)


def get_ticket():
    res = requests.post(TICKET_URL, headers={"X-API-Key": API_KEY})
    return res.json().get("data", {}).get("ticket")


def connect():
    ticket = get_ticket()

    ws = websocket.WebSocketApp(
        WS_URL,
        subprotocols=["bearer", ticket],
        on_open=on_open,
        on_message=on_message,
    )

    ws.run_forever(ping_interval=30)


if __name__ == "__main__":
    print("🔥 BOT STARTING", flush=True)
    connect()
