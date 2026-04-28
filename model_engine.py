import numpy as np
from collections import defaultdict, deque
from statistics import mean, pstdev


class ModelEngineV3:
    def __init__(self):
        self.errors = defaultdict(lambda: defaultdict(lambda: deque(maxlen=100)))
        self.history = defaultdict(list)
        self.leaderboard = {}

    # -------------------------
    # OBSERVATION
    # -------------------------
    def process_observation(self, msg):
        city = msg.get("slug")
        val = msg.get("temperature_f")

        if val is None:
            return

        try:
            val = float(val)
        except:
            return

        print(f"🌡 {city}: {val}", flush=True)

    # -------------------------
    # FORECAST
    # -------------------------
    def process_forecast(self, msg):
        print(f"📊 forecast update {msg.get('slug')}", flush=True)

    # -------------------------
    # ORACLE SCORES (CORE)
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

        snapshot = []

        for s in scores:
            model = s.get("model_id")
            mae = s.get("combined_mae")

            if model is None or mae is None:
                continue

            try:
                mae = float(mae)
            except:
                continue

            self.errors[city][model].append(mae)
            snapshot.append((model, mae))

        if snapshot:
            self.history[city].append(snapshot)

        self.update_dashboard(city)

    # -------------------------
    # WEATHER EVENT (FIXED)
    # -------------------------
    def process_weather_event(self, msg):
        summary = msg.get("summary") or msg.get("type")
        print(f"⚠️ weather: {summary}", flush=True)

    # -------------------------
    # SAFE DASHBOARD UPDATE
    # -------------------------
    def update_dashboard(self, city):
        model_stats = {}

        for model, vals in self.errors[city].items():
            if len(vals) < 3:
                continue

            arr = list(vals)

            avg = mean(arr)
            vol = pstdev(arr) if len(arr) > 1 else 0.0

            mid = len(arr) // 2
            trend = (
                mean(arr[mid:]) - mean(arr[:mid])
                if len(arr) > 4 else 0
            )

            model_stats[model] = {
                "mae": avg,
                "vol": vol,
                "trend": trend,
            }

        if not model_stats:
            print(f"⚠️ {city}: waiting for enough data...", flush=True)
            return

        ranked = sorted(model_stats.items(), key=lambda x: x[1]["mae"])
        self.leaderboard[city] = ranked[:5]

        self.print_dashboard(city, model_stats)

    # -------------------------
    # DASHBOARD (CRASH-PROOF)
    # -------------------------
    def print_dashboard(self, city, stats):
        print("\n" + "=" * 60)
        print(f"🏙 CITY DASHBOARD: {city}")
        print("=" * 60)

        top = self.leaderboard.get(city, [])

        if not top:
            print("⚠️ no ranked models yet")
            return

        best_model = top[0][0]

        stable_model = min(stats.items(), key=lambda x: x[1]["vol"])[0]

        improving = min(
            stats.items(),
            key=lambda x: x[1]["trend"],
        )[0] if stats else None

        avg_vol = (
            sum(v["vol"] for v in stats.values()) / len(stats)
            if stats else 0
        )

        print(f"\n🏆 Best Model: {best_model}")
        print(f"🧊 Most Stable: {stable_model}")
        print(f"📈 Improving: {improving}")
        print(f"⚠️ Volatility: {avg_vol:.3f}")

        print("\n📊 Top Models:")
        for i, (m, s) in enumerate(top, 1):
            print(
                f"{i}. {m} | MAE={s['mae']:.3f} "
                f"| VOL={s['vol']:.3f} "
                f"| TREND={s['trend']:.3f}"
            )

        print("\n🧠 CONCLUSION:")

        if avg_vol < 0.2:
            print("✔ Stable forecasting environment")
        elif avg_vol < 0.5:
            print("⚠ Moderate volatility")
        else:
            print("🚨 High volatility")

        print("=" * 60)

    # -------------------------
    # SAFE HOOK (CRITICAL)
    # -------------------------
    def tick(self):
        pass
