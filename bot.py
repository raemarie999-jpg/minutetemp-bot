import json
import threading
import time
import requests
import websocket

from config import API_KEY, CITIES
from model_engine import ModelEngine

engine = ModelEngine()

LEADERBOARD_EVERY = 10
SNAPSHOT_INTERVAL = 60
event_count = 0


def snapshot_loop():
    while True:
        time.sleep(SNAPSHOT_INTERVAL)
        try:
            engine.snapshot_leaderboard()
        except Exception as e:
            print("Snapshot error:", e)


threading.Thread(target=snapshot_loop, daemon=True).start()


def print_leaderboard():
    by_city = engine.leaderboard_by_city()

    if not by_city:
        return

    print("LEADERBOARD (per city)")

    for city in sorted(by_city.keys()):
        rows = by_city[city]
        print(f"  [{city}]")
        print(f"    {'model':<20} {'avg_error':>10} {'samples':>8}")

        for model, avg_error, samples in rows:
            print(f"    {model:<20} {avg_error:>10.4f} {samples:>8}")

    wins = engine.model_wins()
    if wins:
        total = len(by_city)
        print(f"  WINS (best in N/{total} cities)")
        for model, count in wins:
            print(f"    {model:<20} {count:>3}/{total}")

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
    global event_count

    event = json.loads(message)

    event_type = event.get("type")

    if event_type in ("error", "ack", "subscribed", "subscription"):
        print(f"SERVER {event_type.upper()}:", event)
        return

    engine.process_event(event)

    best = engine.best_model()
    if best:
        print("🔥 BEST MODEL RIGHT NOW:", best)

    event_count += 1
    if event_count % LEADERBOARD_EVERY == 0:
        print_leaderboard()


# 3. WHEN CONNECTED
def on_open(ws):
    print("CONNECTED — subscribing to cities:", CITIES)

    for city in CITIES:
        ws.send(json.dumps({
            "type": "subscribe",
            "cities": [city]
        }))


def on_error(ws, error):
    print("WS ERROR:", error)


def on_close(ws, status_code, msg):
    print(f"WS CLOSED: code={status_code} msg={msg}")


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
                on_message=on_message,
                on_error=on_error,
                on_close=on_close
            )

            ws.run_forever(ping_interval=50)

        except Exception as e:
            print("Error:", e)

        print("Reconnecting...")
        time.sleep(2)


if __name__ == "__main__":
    run()
