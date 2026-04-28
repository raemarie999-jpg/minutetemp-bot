import numpy as np
from collections import defaultdict, deque
from statistics import mean, pstdev


class ModelEngineV3:
    def __init__(self):
        # city -> model -> rolling errors
        self.errors = defaultdict(lambda: defaultdict(lambda: deque(maxlen=100)))

        # raw snapshots for trend detection
        self.history = defaultdict(list)

        self.leaderboard = {}

    # -------------------------
    # OBSERVATION (context only)
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
    # FORECAST (context only)
    # -------------------------
    def process_forecast(self, msg):
        print(f"📊 forecast update {msg.get('slug')}", flush=True)

    # -------------------------
    # ORACLE SCORES (CORE SIGNAL)
    # -------------------------
    def process_oracle_scores(self, msg):
        city = msg.get("slug")
        scores = msg.get("overall", {}).get("scores", []) or msg.get("scores", [])

        if not city:
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
    # DASHBOARD ENGINE
    # -------------------------
    def update_dashboard(self, city):
        if city not in self.errors:
            return

        model_stats = {}

        # compute rolling stats
        for model, vals in self.errors[city].items():
            if len(vals) < 5:
                continue

            arr = list(vals)

            avg = mean(arr)
            vol = pstdev(arr) if len(arr) > 1 else 0.0

            # trend (recent - older)
            mid = len(arr) // 2
            trend = mean(arr[mid:]) - mean(arr[:mid]) if len(arr) > 4 else 0

            model_stats[model] = {
                "mae": avg,
                "vol": vol,
                "trend": trend,
                "stability": max(0, 1 - vol),
            }

        ranked = sorted(model_stats.items(), key=lambda x: x[1]["mae"])
        self.leaderboard[city] = ranked[:5]

        self.print_dashboard(city, model_stats)

    # -------------------------
    # INTELLIGENCE OUTPUT
    # -------------------------
    def print_dashboard(self, city, stats):
        print("\n" + "=" * 60)
        print(f"🏙 CITY INTELLIGENCE DASHBOARD: {city}")
        print("=" * 60)

        if city not in self.leaderboard:
            return

        top = self.leaderboard[city]

        # BEST MODEL
        best_model, best_stats = top[0]

        # MOST STABLE
        stable_model = min(stats.items(), key=lambda x: x[1]["vol"])[0]

        # FASTEST IMPROVING (negative trend)
        improving = sorted(
            stats.items(),
            key=lambda x: x[1]["trend"]
        )[0][0] if stats else None

        # volatility risk
        avg_vol = mean([v["vol"] for v in stats.values()]) if stats else 0

        print(f"\n🏆 Best Model: {best_model}")
        print(f"🧊 Most Stable: {stable_model}")
        print(f"📈 Fastest Improving: {improving}")
        print(f"⚠️ System Volatility: {avg_vol:.3f}")

        print("\n📊 Top 5 Models:")
        for i, (m, s) in enumerate(top, 1):
            print(
                f"{i}. {m} | MAE={s['mae']:.3f} | "
                f"VOL={s['vol']:.3f} | TREND={s['trend']:.3f}"
            )

        # CONCLUSION LAYER
        print("\n🧠 CONCLUSION:")
        if avg_vol < 0.2:
            print("✔ Stable forecasting environment")
        elif avg_vol < 0.5:
            print("⚠ Moderate volatility — model rankings shifting")
        else:
            print("🚨 High volatility — forecasts unreliable right now")

        if stats.get(best_model, {}).get("trend", 0) < 0:
            print("📉 Best model is IMPROVING")

        print("=" * 60)

    # -------------------------
    # SAFE HOOK
    # -------------------------
    def tick(self):
        pass
