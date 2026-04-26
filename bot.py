import json
import time
import requests
import websocket

from config import API_KEY, CITIES
from model_engine import ModelEngine


engine = ModelEngine()

TICKET_URL = "https://api.minutetemp.com/api/v1/ws-ticket"
WS_URL = "wss://api.minutetemp.com/ws/api/1m"


def get_ticket():
    resp = requests.post(
        TICKET_URL,
        headers={"X-API-Key": API_KEY, "Accept": "application/json"}
    )
    resp.raise_for_status()
    return resp.json()["data"]["ticket"]


def on_message(ws, message):
    event = json.loads(message)
    engine.process_event(event)


def on_open(ws):
    print("Connected")

    for city in CITIES:
        ws.send(json.dumps({
            "type": "subscribe",
            "cities": [city]
        }))


def run():
    while True:
        try:
            ticket = get_ticket()

            ws = websocket.WebSocketApp(
                WS_URL,
                subprotocols=["bearer", ticket],
                on_open=on_open,
                on_message=on_message
            )

            ws.run_forever(ping_interval=50)

        except Exception as e:
            print("Error:", e)

        time.sleep(2)


if __name__ == "__main__":
    run()
