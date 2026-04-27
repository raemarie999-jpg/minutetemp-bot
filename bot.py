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

# =========================================================
# 🟢 LIVE TRACKER (FAST PATH)
# =========================================================

def live_observation(msg):
    city = msg.get("slug")
    station = msg.get("station_id")

    temp = (
        msg.get("temperature_f")
        or msg.get("temp_f")
        or msg.get("value")
    )

    try:
        temp_str = f"{float(temp):.1f}°F"
    except (TypeError, ValueError):
        temp_str = "N/A"

    print(f"🌡 LIVE {city} | {station} | {temp_str}", flush=True)

    engine.process_event({
        "type": "observation",
        "city": city,
        "station_id": station,
        "value": temp,
    })


def live_weather_event(msg):
    print("⚠️ WEATHER:", msg.get("summary"), flush=True)


def live_stream_handler(msg):
    msg_type = msg.get("type")

    if msg_type == "observation":
        live_observation(msg)

    elif msg_type == "weather_event":
        live_weather_event(msg)

    elif msg_type == "price_update":
        # optional: keep quiet or log lightly
        pass


# =========================================================
# 🧠 MODEL EVALUATOR (ANALYTICS)
# =========================================================

def model_oracle_scores(msg):
    city = msg.get("slug")
    if not city:
        return

    print("📈 ORACLE SCORES:", city, flush=True)

    engine.process_event({
        "type": "oracle_scores",
        "city": city,
        "station_id": msg.get("station_id"),
        "mode": "overall",
        "scores": msg.get("overall", {}).get("scores", []),
    })


def model_forecast_updated(msg):
    city = msg.get("slug")

    print("📊 FORECAST UPDATED:", city, flush=True)

    # 🔥 trigger evaluation even without new oracle scores
    engine.detect_alerts(city)


def evaluation_handler(msg):
    msg_type = msg.get("type")

    if msg_type == "oracle_scores_updated":
        model_oracle_scores(msg)

    elif msg_type == "forecast_versions":
        print("📊 FORECAST VERSION:", msg.get("slug"), flush=True)

    elif msg_type == "forecast_updated":
        model_forecast_updated(msg)

    elif msg_type == "subscribed":
        print("✅ SUBSCRIBED:", msg.get("accepted"), flush=True)


# =========================================================
# 🔀 ROUTER
# =========================================================

def handle_message(msg):
    msg_type = msg.get("type")
    print("📥 MSG:", msg_type, flush=True)

    # LIVE DATA
    if msg_type in ["observation", "weather_event", "price_update"]:
        live_stream_handler(msg)

    # MODEL / FORECAST DATA
    elif msg_type in [
        "oracle_scores_updated",
        "forecast_versions",
        "forecast_updated",
        "subscribed",
    ]:
        evaluation_handler(msg)

    else:
        print("📩 UNKNOWN:", msg_type, flush=True)

    engine.maybe_send_daily_summary()


# =========================================================
# WEBSOCKET
# =========================================================

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
        print("❌ Ticket failed:", res.text, flush=True)
        return None

    data = res.json()
    return data.get("data", {}).get("ticket") or data.get("ticket")


def on_message(ws, message):
    try:
        data = json.loads(message)
        handle_message(data)
    except Exception as e:
        print("❌ Parse error:", repr(e), flush=True)


def on_open(ws):
    print("🔌 Connected", flush=True)

    for city in CITIES:
        ws.send(json.dumps({
            "type": "subscribe",
            "cities": [city]
        }))
        print(f"📡 Subscribed: {city}", flush=True)


def on_error(ws, error):
    print("❌ WS error:", error, flush=True)


def on_close(ws, code, msg):
    print("🔌 Closed:", code, msg, flush=True)


# =========================================================
# MAIN
# =========================================================

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


if __name__ == "__main__":
    print("🚀 ENTERING MAIN LOOP", flush=True)
    connect()
