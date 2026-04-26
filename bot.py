import json
import time
import requests
import websocket

from config import API_KEY, CITIES
from model_engine import ModelEngine

engine = ModelEngine()

TICKET_URL = "https://api.minutetemp.com/api/v1/ws-ticket"
WS_URL = "wss://api.minutetemp.com/ws/api/1m"


# 1. GET TICKET (every time)
def get_ticket():
    resp = requests.post(
        TICKET_URL,
        headers={
            "X-API-Key": API_KEY,
            "Accept": "application/json"
        }
    )
    resp.raise_for_status()
    return resp.json()["data"]["ticket"]


# 2. WHEN DATA COMES IN
def on_message(ws, message):
    event = json.loads(message)

    engine.process_event(event)

    best = engine.best_model()
    if best:
        print("🔥 BEST MODEL RIGHT NOW:", best)


# 3. WHEN CONNECTED
def on_open(ws):
    print("CONNECTED")

    ws.send(json.dumps({
        "type": "subscribe",
        "cities": CITIES
    }))


# 4. MAIN LOOP
def run():
    while True:
        try:
            print("Getting ticket...")
            ticket = get_ticket()

            print("Opening WebSocket...")

            ws = websocket.WebSocketApp(
                WS_URL,
                subprotocols=["bearer", ticket],
                on_open=on_open,
                on_message=on_message
            )

            ws.run_forever(ping_interval=50)

        except Exception as e:
            print("Error:", e)

        print("Reconnecting...")
        time.sleep(2)


if __name__ == "__main__":
    run()
