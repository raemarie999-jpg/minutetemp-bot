import numpy as np
from collections import defaultdict, deque


class ModelEngineV2:
    def __init__(self):
        self.errors = defaultdict(lambda: defaultdict(lambda: deque(maxlen=50)))
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
        print(f"📊 forecast {msg.get('slug')}", flush=True)

    # -------------------------
    # ORACLE SCORES (CORE)
    # -------------------------
    def process_oracle_scores(self, msg):
        city = msg.get("slug")
        scores = msg.get("overall", {}).get("scores", []) or msg.get("scores", [])

        if not city:
            return

        for s in scores:
            mid = s.get("model_id")
            mae = s.get("combined_mae")

            if mid is None or mae is None:
                continue

            try:
                mae = float(mae)
            except:
                continue

            self.errors[city][mid].append(mae)

        self.update(city)

    # -------------------------
    # WEATHER
    # -------------------------
    def process_weather_event(self, msg):
        print("⚠️ weather:", msg.get("summary"), flush=True)

    # -------------------------
    # LEADERBOARD
    # -------------------------
    def update(self, city):
        scores = {}

        for m, vals in self.errors[city].items():
            if len(vals) < 3:
                continue
            scores[m] = float(np.mean(vals))

        ranked = sorted(scores.items(), key=lambda x: x[1])[:5]
        self.leaderboard[city] = ranked

        self.print(city)

    def print(self, city):
        print(f"\n🏆 {city} leaderboard", flush=True)
        for i, (m, s) in enumerate(self.leaderboard.get(city, []), 1):
            print(f"{i}. {m} → {s:.3f}", flush=True)

    # -------------------------
    # SAFE HOOK (CRITICAL FIX)
    # -------------------------
    def tick(self):
        pass
