import json
import os
import sys
import time
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
    msg_type = msg.get("type")
    print("📥 HANDLE:", msg_type, flush=True)

    # -------------------------
    # SUBSCRIBED
    # -------------------------
    if msg_type == "subscribed":
        print("✅ SUBSCRIBED:", msg.get("accepted"), flush=True)

    # -------------------------
    # OBSERVATION (MAIN DATA STREAM)
    # -------------------------
    elif msg_type == "observation":
        city = msg.get("slug")
        station_id = msg.get("station_id")

        temp_f = (
            msg.get("temperature_f")
            or msg.get("temp_f")
            or msg.get("value")
        )

        try:
            temp_display = f"{float(temp_f):.1f}°F"
        except (TypeError, ValueError):
            temp_display = "N/A"

        print(
            f"🌡 OBSERVATION {city} | {station_id} | {temp_display}",
            flush=True,
        )

        engine.process_event({
            "type": "observation",
            "city": city,
            "station_id": station_id,
            "value": temp_f,
        })

    # -------------------------
    # FORECAST METADATA
    # -------------------------
    elif msg_type == "forecast_versions":
        print("📊 FORECAST UPDATE:", msg.get("slug"), flush=True)

    # -------------------------
    # ORACLE SCORES (MODEL EVALUATION)
    # -------------------------
    elif msg_type == "oracle_scores_updated":
        print("📈 MODEL SCORES UPDATED:", msg.get("slug"), flush=True)

        engine.process_event({
            "type": "oracle_scores",
            "city": msg.get("slug"),
            "station_id": msg.get("station_id"),
            "mode": "overall",
            "scores": msg.get("overall", {}).get("scores", []),
        })

    # -------------------------
    # WEATHER EVENTS
    # -------------------------
    elif msg_type == "weather_event":
        print("⚠️ WEATHER EVENT:", msg.get("summary"), flush=True)

    # -------------------------
    # IGNORE PRICE NOISE (OPTIONAL)
    # -------------------------
    elif msg_type in ["price_update", "forecast_updated"]:
        print("📩 IGNORED:", msg_type, flush=True)

    # -------------------------
    # FALLBACK
    # -------------------------
    else:
        print("📩 UNKNOWN:", msg_type, msg, flush=True)

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
# GET TICKET (ONLY ONCE)
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
        print("❌ Failed to get ticket:", res.text, flush=True)
        return None

    data = res.json()
    inner = data.get("data")

    if isinstance(inner, dict):
        return inner.get("ticket")

    return data.get("ticket")


# -------------------------
# CONNECT (SINGLE SESSION)
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
