import json
import websocket
import requests

# 🔑 YOUR API KEY (this part you already had correct)
API_KEY = "mt_663bb9c8e723a581d28130ddde325251694d086d9753f009cd7019348435e5c9"

# ✅ CORRECT ENDPOINTS
TICKET_URL = "https://api.minutetemp.com/v1/tickets"
WS_BASE = "wss://stream.minutetemp.com/v1/realtime"

CITIES = ["nyc"]

print("🔥 BOT STARTING")
print("🌍 CITIES:", CITIES)


# -------------------------
# GET WEBSOCKET TICKET
# -------------------------
def get_ticket():
    print("📡 Requesting ticket...")

    headers = {
        "Authorization": f"Bearer {API_KEY}"
    }

    res = requests.post(TICKET_URL, headers=headers)

    print("📨 Ticket status:", res.status_code)

    if res.status_code != 200:
        print("❌ Failed to get ticket")
        print(res.text)
        return None

    data = res.json()
    print("📨 Ticket response:", data)

    # Most Minutetemp responses use this shape:
    # { "ticket": "xxxx" }
    return data.get("ticket")


# -------------------------
# MESSAGE HANDLER
# -------------------------
def handle_message(msg):
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
        print(msg.get("summary"))

    elif msg_type == "forecast_versions":
        print("\n📊 FORECAST UPDATE")
        print(msg.get("slug"), msg.get("station_id"))

    elif msg_type == "oracle_scores_updated":
        print("\n📈 MODEL SCORES UPDATED")
        print(msg.get("slug"))

    else:
        print("\n📩 OTHER:", msg_type)


# -------------------------
# WEBSOCKET CALLBACKS
# -------------------------
def on_message(ws, message):
    try:
        data = json.loads(message)
        handle_message(data)
    except Exception as e:
        print("❌ Parse error:", e)


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


# -------------------------
# MAIN
# -------------------------
if __name__ == "__main__":
    print("🚀 ENTERING MAIN LOOP")

    ticket = get_ticket()

    if not ticket:
        print("❌ No ticket — exiting")
        exit(1)

    print("🎟 Ticket:", ticket)

    WS_URL = f"{WS_BASE}?ticket={ticket}"

    print("🔌 Opening WebSocket...")

    ws = websocket.WebSocketApp(
        WS_URL,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )

    ws.run_forever()
