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
# LIVE TRACKER
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
    except:
        temp_str = "N/A"

    print(f"🌡 LIVE {city} | {station} | {temp_str}", flush=True)

    engine.process_event({
        "type": "observation",
        "city": city,
        "station_id": station,
        "value": temp,
    })


def live_stream_handler(msg):
    if msg.get("type") == "observation":
        live_observation(msg)


# =========================================================
# MODEL EVALUATOR (MULTI-MODE)
# =========================================================

def extract_scores(msg, mode):
    block = msg.get(mode)
    if not isinstance(block, dict):
        return []
    return block.get("scores", [])


def model_oracle_scores(msg):
    city = msg.get("slug")
    if not city:
        return

    print("📈 ORACLE UPDATE:", city, flush=True)

    for mode in ["overall", "day_ahead", "day_of"]:
        scores = extract_scores(msg, mode)

        if not scores:
            continue

        engine.process_event({
            "type": "oracle_scores",
            "city": city,
            "station_id": msg.get("station_id"),
            "mode": mode,
            "scores": scores,
        })


def model_forecast_updated(msg):
    city = msg.get("slug")

    print("📊 FORECAST UPDATED:", city, flush=True)

    # trigger re-evaluation using latest multi-mode data
    engine.detect_alerts(city)


def evaluation_handler(msg):
    msg_type = msg.get("type")

    if msg_type == "oracle_scores_updated":
        model_oracle_scores(msg)

    elif msg_type == "forecast_updated":
        model_forecast_updated(msg)

    elif msg_type == "forecast_versions":
        print("📊 FORECAST VERSION:", msg.get("slug"), flush=True)

    elif msg_type == "subscribed":
        print("✅ SUBSCRIBED:", msg.get("accepted"), flush=True)


# =========================================================
# ROUTER
# =========================================================

def handle_message(msg):
    msg_type = msg.get("type")
    print("📥 MSG:", msg_type, flush=True)

    if msg_type == "observation":
        live_stream_handler(msg)

    elif msg_type in [
        "oracle_scores_updated",
        "forecast_updated",
        "forecast_versions",
        "subscribed",
    ]:
        evaluation_handler(msg)

    engine.maybe_send_daily_summary()


# =========================================================
# WEBSOCKET
# =========================================================

def get_ticket():
    print("📡 Requesting ticket...", flush=True)

    res = requests.post(
        TICKET_URL,
        headers={"X-API-Key": API_KEY},
        timeout=10,
    )

    print("📨 Ticket status:", res.status_code, flush=True)

    if res.status_code != 200:
        print("❌ Ticket failed:", res.text, flush=True)
        return None

    data = res.json()
    return data.get("data", {}).get("ticket") or data.get("ticket")


def on_message(ws, message):
    try:
        handle_message(json.loads(message))
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

    ws = websocket.WebSocketApp(
        WS_URL,
        subprotocols=["bearer", ticket],
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )

    ws.run_forever(ping_interval=30, ping_timeout=10)


if __name__ == "__main__":
    print("🚀 ENTERING MAIN LOOP", flush=True)
    connect()
