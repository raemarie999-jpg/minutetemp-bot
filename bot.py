import json
import websocket

CITIES = ["nyc"]

print("🔥 BOT STARTING")
print("🌍 CITIES:", CITIES)


def safe_get(msg, key, default=None):
    return msg.get(key, default)


def handle_message(msg):
    if not isinstance(msg, dict):
        print("⚠️ Non-dict message received")
        print(msg)
        return

    msg_type = msg.get("type")

    if msg_type == "subscribed":
        print("✅ SUBSCRIBED")
        print("Accepted:", msg.get("accepted"))

    elif msg_type == "observation":
        print("\n🌡 OBSERVATION")
        print(f"{msg.get('slug')} | {msg.get('station_id')}")
        print(f"Temp: {msg.get('temperature_f')}°F")

    elif msg_type == "weather_event":
        print("\n⚠️ WEATHER EVENT")
        print(msg.get("summary", "No summary"))

    elif msg_type == "forecast_versions":
        versions = msg.get("versions", {})
        print("\n📊 FORECAST UPDATE")
        print(f"{msg.get('slug')} ({msg.get('station_id')})")
        print(f"Models: {len(versions)}")

    elif msg_type == "oracle_scores_updated":
        print("\n📈 MODEL SCORES UPDATED")
        print(msg.get("slug"))
        print("Modes:", msg.get("modes"))

    elif msg_type is None:
        print("⚠️ Message missing type field")
        print(msg)

    else:
        print("\n📩 UNHANDLED MESSAGE TYPE:", msg_type)
        print(msg)


def on_message(ws, message):
    try:
        data = json.loads(message)
        handle_message(data)

    except json.JSONDecodeError:
        print("❌ Invalid JSON received")
        print(message)

    except Exception as e:
        print("❌ Handler crash:", e)
        print(message)


def on_open(ws):
    print("🔌 WebSocket connected")

    payload = {
        "type": "subscribe",
        "cities": CITIES
    }

    ws.send(json.dumps(payload))
    print("📡 Subscribed to cities")


def on_error(ws, error):
    print("❌ WebSocket error:", error)


def on_close(ws, close_status_code, close_msg):
    print("🔌 WebSocket closed:", close_status_code, close_msg)


if __name__ == "__main__":
    print("🚀 ENTERING MAIN LOOP")

    WS_URL = "wss://YOUR_WEBSOCKET_URL_HERE"

    if "YOUR_WEBSOCKET_URL_HERE" in WS_URL:
        print("❌ ERROR: WebSocket URL is not set")
        exit(1)

    ws = websocket.WebSocketApp(
        WS_URL,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )

    ws.run_forever()
