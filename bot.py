import json
import time
import requests
import websocket
import traceback
import sys

from config import API_KEY, CITIES
from model_engine import ModelEngine


# -------------------------
# FORCE REAL-TIME LOGGING
# -------------------------
sys.stdout.reconfigure(line_buffering=True)

engine = ModelEngine()

TICKET_URL = "https://api.minutetemp.com/api/v1/ws-ticket"
WS_URL = "wss://api.minutetemp.com/ws/api/1m"


# -------------------------
# STARTUP CHECK
# -------------------------
print("🔥 BOT STARTING", flush=True)
print("🔑 API KEY LOADED:", bool(API_KEY), flush=True)
print("🌍 CITIES:", CITIES, flush=True)


# -------------------------
# GET WEBSOCKET TICKET
# -------------------------
def get_ticket():
    print("📡 Requesting ticket...", flush=True)

    try:
        resp = requests.post(
            TICKET_URL,
            headers={
                "X-API-Key": API_KEY,
                "Accept": "application/json"
            },
            timeout=10
        )

        print("📨 Ticket status:", resp.status_code, flush=True)

        data = resp.json()

        if "data" not in data or "ticket" not in data["data"]:
            raise ValueError(f"Bad ticket response: {data}")

        ticket = data["data"]["ticket"]

        print("🎟 Ticket received OK", flush=True)
        return ticket

    except Exception as e:
        print("❌ Ticket request failed:", repr(e), flush=True)
        raise


# -------------------------
# WEBSOCKET EVENTS
# -------------------------
def on_message(ws, message):
    try:
        event = json.loads(message)
        engine.process_event(event)
    except Exception as e:
        print("❌ Message error:", repr(e), flush=True)


def on_open(ws):
    print("✅ WebSocket connected", flush=True)

    for city in CITIES:
        ws.send(json.dumps({
            "type": "subscribe",
            "cities": [city]
        }))

    print("📡 Subscribed to cities", flush=True)


def on_error(ws, error):
    print("⚠️ WebSocket error:", repr(error), flush=True)


def on_close(ws, code, msg):
    print(f"🔌 WebSocket closed: {code} {msg}", flush=True)


# -------------------------
# MAIN LOOP
# -------------------------
def run():
    print("🚀 ENTERING MAIN LOOP", flush=True)

    while True:
        try:
            ticket = get_ticket()

            print("🔌 Opening WebSocket...", flush=True)

            ws = websocket.WebSocketApp(
                WS_URL,
                subprotocols=["bearer", ticket],
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close
            )

            ws.run_forever(ping_interval=50)

        except Exception:
            print("❌ CRASH OCCURRED:", flush=True)
            print(traceback.format_exc(), flush=True)

        print("♻️ Restarting in 3 seconds...", flush=True)
        time.sleep(3)


# -------------------------
# ENTRY POINT
# -------------------------
if __name__ == "__main__":
    run()
