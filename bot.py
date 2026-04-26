import json
import websocket

CITIES = ["nyc"]

print("🔥 BOT STARTING")
print("🌍 CITIES:", CITIES)


def handle_message(msg):
    msg_type = msg.get("type")

    if msg_type == "subscribed":
        print("✅ SUBSCRIBED")
        print("Accepted:", msg.get("accepted"))

    elif msg_type == "observation":
        print("\n🌡 OBSERVATION")
        print(f"{msg['slug']} | {msg['station_id']}")
        print(f"Temp: {msg['temperature_f']}°F")

    elif msg_type == "weather_event":
        print("\n⚠️ WEATHER EVENT")
        print(msg.get("summary", "No summary"))

    elif msg_type == "forecast_versions":
        print("\n📊 FORECAST UPDATE")
        print(f"{msg['slug']} ({msg['station_id']})")
        print(f"Models: {len(msg['versions'])}")

    elif msg_type == "oracle_scores_updated":
        print("\n📈 MODEL SCORES UPDATED")
        print(msg.get("slug"))
        print("Modes:", msg.get("modes"))

    else:
        print("\n📩 UNKNOWN MESSAGE")
        print(msg)


def on_message(ws, message):
    try:
        data = json.loads(message)
        handle_message(data)
    except Exception as e:
        print("❌ Error parsing message:", e)
        print(message)


def on_open(ws):
    print("🔌 WebSocket connected")
    ws.send(json.dumps({
        "type": "subscribe",
        "cities": CITIES
    }))
    print("📡 Subscribed to cities")


def on_error(ws, error):
    print("❌ WebSocket error:", error)


def on_close(ws, close_status_code, close_msg):
    print("🔌 WebSocket closed", close_status_code, close_msg)


if __name__ == "__main__":
    print("🚀 ENTERING MAIN LOOP")

    ws = websocket.WebSocketApp(
        "wss://YOUR_WEBSOCKET_URL_HERE",
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )

    ws.run_forever()
