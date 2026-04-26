import json
import time
import requests
import websocket
import traceback

from config import API_KEY, CITIES
from model_engine import ModelEngine

engine = ModelEngine()

TICKET_URL = "https://api.minutetemp.com/api/v1/ws-ticket"
WS_URL = "wss://api.minutetemp.com/ws/api/1m"


print("🚀 BOT STARTING")
print("API KEY LOADED:", bool(API_KEY))


def get_ticket():
    print("📡 Requesting ticket...")

    resp = requests.post(
        TICKET_URL,
        headers={"X-API-Key": API_KEY},
        timeout=10
    )

    print("Ticket status:", resp.status_code)

    data = resp.json()
    print("Ticket response received")

    return data["data"]["ticket"]


def on_message(ws, message):
    engine.process_event(json.loads(message))


def on_open(ws):
    print("✅ Connected")

    for city in CITIES:
        ws.send(json.dumps({
            "type": "subscribe",
            "cities": [city]
        }))


def run():
    while True:
        try:
            ticket = get_ticket()
            print("🎟 Ticket OK")

            ws = websocket.WebSocketApp(
                WS_URL,
                subprotocols=["bearer", ticket],
                on_open=on_open,
                on_message=on_message,
                on_error=lambda ws, e: print("WS ERROR:", e),
                on_close=lambda ws, c, m: print("WS CLOSED:", c, m),
            )

            ws.run_forever(ping_interval=50)

        except Exception:
            print("❌ CRASH")
            print(traceback.format_exc())

        time.sleep(3)


if __name__ == "__main__":
    run()
