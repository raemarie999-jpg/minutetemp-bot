import time
import numpy as np
from collections import defaultdict, deque
from statistics import mean, pstdev


class ModelEngineV4:
    def __init__(self):
        # -------------------------
        # MODEL PERFORMANCE STORAGE
        # -------------------------
        self.errors = defaultdict(lambda: defaultdict(lambda: deque(maxlen=300)))

        # -------------------------
        # DASHBOARD STATE
        # -------------------------
        self.last_dashboard_time = defaultdict(float)
        self.dashboard_interval = 60  # seconds

        self.last_best_model = {}

    # =========================================================
    # OBSERVATIONS
    # =========================================================
    def process_observation(self, msg):
        city = msg.get("slug")
        val = msg.get("temperature_f")

        try:
            if val is None:
                return
            val = float(val)
        except:
            return

        print(f"🌡 {city}: {val}", flush=True)

    # =========================================================
    # FORECASTS (INFO ONLY)
    # =========================================================
    def process_forecast(self, msg):
        print(f"📊 forecast update {msg.get('slug')}", flush=True)

    # =========================================================
    # WEATHER EVENTS (CONTEXT ONLY)
    # =========================================================
    def process_weather_event(self, msg):
        print(f"⚠️ weather event: {msg.get('summary')}", flush=True)

    # =========================================================
    # ORACLE SCORES (CORE INPUT)
    # =========================================================
    def process_oracle_scores(self, msg):
        city = msg.get("slug")
        if not city:
            return

        scores = (
            msg.get("overall", {}).get("scores", [])
            or msg.get("day_ahead", {}).get("scores", [])
            or msg.get("scores", [])
        )

        if not scores:
            return

        for s in scores:
            model = s.get("model_id")
            mae = s.get("combined_mae")

            try:
                mae = float(mae)
            except:
                continue

            self.errors[city][model].append(mae)

        self.update_dashboard(city)

    # =========================================================
    # DASHBOARD BUILDER
    # =========================================================
    def build_dashboard(self, city):
        models = self.errors[city]

        stats = []

        for model, vals in models.items():
            if len(vals) < 5:
                continue

            arr = list(vals)

            mae = mean(arr)
            vol = pstdev(arr) if len(arr) > 1 else 0.0
            trend = arr[-1] - arr[0] if len(arr) > 1 else 0.0

            score = mae + (0.5 * vol) + (0.2 * abs(trend))

            stats.append({
                "model": model,
                "mae": mae,
                "vol": vol,
                "trend": trend,
                "score": score
            })

        if not stats:
            return None

        stats.sort(key=lambda x: x["score"])

        best = stats[0]

        avg_vol = mean([s["vol"] for s in stats])

        if avg_vol < 0.2:
            state = "STABLE"
        elif avg_vol < 0.5:
            state = "MODERATE"
        else:
            state = "UNSTABLE"

        confidence = 1 / (1 + best["score"])

        return {
            "city": city,
            "best": best["model"],
            "confidence": confidence,
            "state": state,
            "top_models": stats[:5]
        }

    # =========================================================
    # DASHBOARD OUTPUT (FINAL USER VIEW)
    # =========================================================
    def render_dashboard(self, city):
        dash = self.build_dashboard(city)

        if not dash:
            print(f"⚠️ {city}: warming up (insufficient data)", flush=True)
            return

        prev = self.last_best_model.get(city)

        self.last_best_model[city] = dash["best"]

        print("\n" + "=" * 70)
        print(f"🏙 LIVE MODEL DASHBOARD: {city}")
        print("=" * 70)

        print(f"🏆 Best Model: {dash['best']}")
        print(f"🎯 Confidence: {dash['confidence']:.2f}")
        print(f"🧠 State: {dash['state']}")

        if prev and prev != dash["best"]:
            print(f"🔁 MODEL SWITCH: {prev} → {dash['best']}")

        print("\n📊 TOP 5 MODELS")

        for m in dash["top_models"]:
            print(
                f"- {m['model']} | "
                f"MAE={m['mae']:.2f} | "
                f"VOL={m['vol']:.2f} | "
                f"TREND={m['trend']:.2f}"
            )

        print("=" * 70)

    # =========================================================
    # DASHBOARD UPDATE TRIGGER (SAFE + STABLE)
    # =========================================================
    def update_dashboard(self, city):
        now = time.time()

        if now - self.last_dashboard_time[city] < self.dashboard_interval:
            return

        self.last_dashboard_time[city] = now
        self.render_dashboard(city)
