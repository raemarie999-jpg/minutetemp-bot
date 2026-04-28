import time
import numpy as np
from collections import defaultdict, deque
from statistics import mean, pstdev


class ModelEngineV4:
    def __init__(self):
        # -------------------------
        # DATA STORAGE
        # -------------------------
        self.errors = defaultdict(lambda: defaultdict(lambda: deque(maxlen=200)))

        # -------------------------
        # REPORTING CONTROL
        # -------------------------
        self.last_report_time = defaultdict(float)
        self.report_interval = 60  # seconds

        # -------------------------
        # DECISION STATE
        # -------------------------
        self.last_best_model = {}
        self.model_confidence = defaultdict(dict)

    # =========================================================
    # OBSERVATIONS (SAFE PASS-THROUGH)
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
    # FORECASTS (FUTURE USE)
    # =========================================================
    def process_forecast(self, msg):
        print(f"📊 forecast update {msg.get('slug')}", flush=True)

    # =========================================================
    # WEATHER EVENTS
    # =========================================================
    def process_weather_event(self, msg):
        print(f"⚠️ weather: {msg.get('summary')}", flush=True)

    # =========================================================
    # ORACLE SCORES (CORE SYSTEM INPUT)
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

        # -------------------------
        # TRIGGER REPORTS (TIME BASED)
        # -------------------------
        now = time.time()

        if now - self.last_report_time[city] > self.report_interval:
            self.last_report_time[city] = now

            self.generate_report(city)
            self.evaluate_city(city)

    # =========================================================
    # REPORT LAYER (HUMAN READABLE)
    # =========================================================
    def generate_report(self, city):
        models = self.errors[city]

        stats = []

        for model, vals in models.items():
            if len(vals) < 3:
                continue

            arr = list(vals)

            mae = mean(arr)
            vol = pstdev(arr) if len(arr) > 1 else 0.0
            trend = arr[-1] - arr[0] if len(arr) > 1 else 0.0

            stats.append((model, mae, vol, trend))

        if not stats:
            print(f"⚠️ {city}: warming up (no report yet)", flush=True)
            return

        stats.sort(key=lambda x: x[1])

        best = stats[0]
        worst = stats[-1]

        avg_vol = mean([s[2] for s in stats])

        state = (
            "STABLE" if avg_vol < 0.2
            else "MODERATE" if avg_vol < 0.5
            else "UNSTABLE"
        )

        print("\n" + "=" * 60)
        print(f"📊 CITY REPORT: {city}")
        print("=" * 60)

        print(f"🏆 Best Model: {best[0]} | MAE {best[1]:.2f}")
        print(f"⚠️ Worst Model: {worst[0]} | MAE {worst[1]:.2f}")
        print(f"🧠 Market State: {state}")
        print(f"📉 Volatility: {avg_vol:.3f}")

        print("\n📈 Top Models:")
        for m in stats[:5]:
            print(f"- {m[0]} | MAE={m[1]:.2f} | VOL={m[2]:.2f}")

        print("=" * 60)

    # =========================================================
    # DECISION LAYER (MACHINE INTELLIGENCE)
    # =========================================================
    def evaluate_city(self, city):
        models = self.errors[city]

        scored = {}

        for model, vals in models.items():
            if len(vals) < 5:
                continue

            arr = np.array(vals)

            mae = np.mean(arr)
            vol = np.std(arr)
            trend = arr[-1] - arr[0]

            # lower is better
            score = mae + (0.5 * vol) + (0.2 * abs(trend))

            scored[model] = score

        if not scored:
            return

        best_model = min(scored, key=scored.get)

        confidence = 1.0 / (1.0 + scored[best_model])

        prev_best = self.last_best_model.get(city)

        # -------------------------
        # FLIP DETECTION
        # -------------------------
        if prev_best and prev_best != best_model:
            print("\n🔁 MODEL FLIP DETECTED")
            print(f"🏙 {city}: {prev_best} → {best_model}", flush=True)

        self.last_best_model[city] = best_model

        self.model_confidence[city][best_model] = confidence

        # -------------------------
        # DECISION OUTPUT
        # -------------------------
        print("\n🧠 DECISION UPDATE")
        print(f"🏙 City: {city}")
        print(f"🏆 Best Model: {best_model}")
        print(f"🎯 Confidence: {confidence:.3f}")

        top = sorted(scored.items(), key=lambda x: x[1])[:3]

        print("\n🥇 Ranked Models:")
        for m, s in top:
            print(f"- {m} | score={s:.3f}")

        print("=" * 60)

    # =========================================================
    # SAFE HOOK (BOT COMPATIBILITY)
    # =========================================================
    def tick(self):
        pass
