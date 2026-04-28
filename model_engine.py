import numpy as np
from collections import defaultdict, deque
from statistics import mean, pstdev


class ModelEngineV3:
    def __init__(self):
        self.errors = defaultdict(lambda: defaultdict(lambda: deque(maxlen=100)))
        self.report_counter = defaultdict(int)
        self.leaderboard = {}

    # -------------------------
    # OBSERVATION
    # -------------------------
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

    # -------------------------
    # FORECAST
    # -------------------------
    def process_forecast(self, msg):
        print(f"📊 forecast {msg.get('slug')}", flush=True)

    # -------------------------
    # ORACLE SCORES
    # -------------------------
    def process_oracle_scores(self, msg):
        city = msg.get("slug")

        scores = (
            msg.get("overall", {}).get("scores", [])
            or msg.get("day_ahead", {}).get("scores", [])
            or msg.get("scores", [])
        )

        if not city or not scores:
            return

        for s in scores:
            model = s.get("model_id")
            mae = s.get("combined_mae")

            try:
                mae = float(mae)
            except:
                continue

            self.errors[city][model].append(mae)

        self.report_counter[city] += 1

        if self.report_counter[city] % 5 == 0:
            self.generate_report(city)

    # -------------------------
    # WEATHER
    # -------------------------
    def process_weather_event(self, msg):
        print("⚠️ weather:", msg.get("summary"), flush=True)

    # -------------------------
    # SAFE REPORT GENERATION
    # -------------------------
    def generate_report(self, city):
        models = self.errors[city]

        stats = []

        for m, vals in models.items():
            if len(vals) < 3:
                continue

            arr = list(vals)

            mae = mean(arr)
            vol = pstdev(arr) if len(arr) > 1 else 0
            trend = arr[-1] - arr[0]

            stats.append((m, mae, vol, trend))

        if not stats:
            print(f"⚠️ {city}: warming up...", flush=True)
            return

        stats.sort(key=lambda x: x[1])

        best = stats[0]
        worst = stats[-1]

        vol_avg = mean([s[2] for s in stats])

        state = (
            "STABLE" if vol_avg < 0.2
            else "MODERATE" if vol_avg < 0.5
            else "UNSTABLE"
        )

        print("\n" + "=" * 60)
        print(f"📊 CITY REPORT: {city}")
        print("=" * 60)

        print(f"🏆 Best: {best[0]} | MAE {best[1]:.2f}")
        print(f"⚠️ Worst: {worst[0]} | MAE {worst[1]:.2f}")
        print(f"🧠 State: {state}")
        print(f"📉 Volatility: {vol_avg:.3f}")

        print("\n📈 Top Models:")
        for m in stats[:5]:
            print(f"- {m[0]} | MAE={m[1]:.2f} | VOL={m[2]:.2f}")

        print("=" * 60)

    # -------------------------
    # SAFE HOOK
    # -------------------------
    def tick(self):
        pass
