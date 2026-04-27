import json
import os
import sys
import requests
import websocket

from model_engine import ModelEngine

# -------------------------
# CONFIG
# -------------------------
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
    for c in os.getenv("CITIES", "nyc").split(",")
    if c.strip()
]

print("🔥 BOT STARTING", flush=True)
print("🌍 CITIES:", CITIES, flush=True)

if not API_KEY:
    print("❌ MINUTETEMP_API_KEY not set", flush=True)
    sys.exit(1)

engine = ModelEngine()

# -------------------------
# MESSAGE HANDLER
# -------------------------
def handle_message(msg):
    print("📥 HANDLE:", msg.get("type"), flush=True)
    msg_type = msg.get("type")

    if msg_type == "subscribed":
        print("✅ SUBSCRIBED", msg.get("accepted"), flush=True)

elif msg_type == "observation":
    temp_f = msg.get("temperature_f")

    # fallback safety (API sometimes sends different shapes or nulls)
    if temp_f is None:
        temp_f = msg.get("temp_f")
    if temp_f is None:
        temp_f = msg.get("value")

    try:
        temp_str = f"{float(temp_f):.1f}°F"
    except (TypeError, ValueError):
        temp_str = "N/A"

    print(
        f"\n🌡 OBSERVATION {msg.get('slug')} | "
        f"{msg.get('station_id')} | "
        f"{temp_str}",
        flush=True,
    )

    engine.process_event({
        "type": "observation",
        "city": msg.get("slug"),
        "station_id": msg.get("station_id"),
        "value": temp_f,
    })
        engine.process_event({
            "type": "observation",
            "city": msg.get("slug"),
            "station_id": msg.get("station_id"),
            "value": msg.get("temperature_f"),
        })

    elif msg_type == "forecast_versions":
        print("\n📊 FORECAST UPDATE", msg.get("slug"), flush=True)

    elif msg_type == "oracle_scores_updated":
        print("\n📈 MODEL SCORES UPDATED", msg.get("slug"), flush=True)

        engine.process_event({
            "type": "oracle_scores",
            "city": msg.get("slug"),
            "station_id": msg.get("station_id"),
            "mode": "overall",
            "scores": msg.get("overall", {}).get("scores", []),
        })

    elif msg_type == "weather_event":
        print("\n⚠️ WEATHER EVENT", msg.get("summary"), flush=True)

    else:
        print("\n📩 MSG:", msg_type, flush=True)

    engine.maybe_send_daily_summary()


# -------------------------
# WEBSOCKET CALLBACKS
# -------------------------
def on_message(ws, message):
    try:
        data = json.loads(message)
        handle_message(data)
    except Exception as e:
        print("❌ Parse error:", repr(e), flush=True)


def on_open(ws):
    print("🔌 WebSocket connected", flush=True)

    for city in CITIES:
        ws.send(json.dumps({
            "type": "subscribe",
            "cities": [city]
        }))
        print(f"📡 Subscribed: {city}", flush=True)


def on_error(ws, error):
    print("❌ WebSocket error:", error, flush=True)


def on_close(ws, close_status_code, close_msg):
    print("🔌 WebSocket closed", close_status_code, close_msg, flush=True)


# -------------------------
# GET TICKET (ONCE ONLY)
# -------------------------
def get_ticket():
    print("📡 Requesting ticket...", flush=True)

    try:
        res = requests.post(
            TICKET_URL,
            headers={"X-API-Key": API_KEY},
            timeout=10,
        )
    except Exception as e:
        print("❌ Ticket request error:", repr(e), flush=True)
        return None

    print("📨 Ticket status:", res.status_code, flush=True)

    if res.status_code != 200:
        print("❌ Failed to get ticket", flush=True)
        print(res.text, flush=True)
        return None

    data = res.json()

    inner = data.get("data")
    if isinstance(inner, dict):
        return inner.get("ticket")

    return data.get("ticket")


# -------------------------
# SINGLE CONNECTION (MODEL A)
# -------------------------
def connect():
    ticket = get_ticket()

    if not ticket:
        print("❌ No ticket — exiting", flush=True)
        return

    print("🔌 Opening WebSocket...", flush=True)

    ws = websocket.WebSocketApp(
        WS_URL,
        subprotocols=["bearer", ticket],
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )

    ws.run_forever(
        ping_interval=30,
        ping_timeout=10,
    )


# -------------------------
# MAIN
# -------------------------
if __name__ == "__main__":
    print("🚀 ENTERING MAIN LOOP", flush=True)
    connect()
