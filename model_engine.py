import numpy as np
from collections import defaultdict, deque
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ModelEngineV2:
    """
    Live model ranking engine:
    - tracks oracle MAE over time
    - builds per-city leaderboard
    - handles observations + forecasts + scores
    """

    def __init__(self):
        # city -> model -> rolling errors
        self.errors = defaultdict(lambda: defaultdict(lambda: deque(maxlen=50)))

        # last computed leaderboard cache
        self.leaderboard = {}

    # -------------------------
    # OBSERVATIONS
    # -------------------------
    def process_observation(self, msg):
        city = msg.get("slug")
        value = msg.get("temperature_f")

        if city and value is not None:
            print(f"🌡 OBS {city}: {value}", flush=True)

    # -------------------------
    # FORECASTS
    # -------------------------
    def process_forecast(self, msg):
        city = msg.get("slug")
        print(f"📊 FORECAST {city}", flush=True)

    # -------------------------
    # ORACLE SCORES (CORE)
    # -------------------------
    def process_oracle_scores(self, msg):
        city = msg.get("slug")
        station = msg.get("station_id")
        scores = msg.get("overall", {}).get("scores", []) or msg.get("scores", [])

        if not city:
            return

        for s in scores:
            model_id = s.get("model_id")
            mae = s.get("combined_mae")

            if model_id is None or mae is None:
                continue

            try:
                mae = float(mae)
            except:
                continue

            self.errors[city][model_id].append(mae)

        self.update_leaderboard(city)

    # -------------------------
    # WEATHER EVENTS
    # -------------------------
    def process_weather_event(self, msg):
        print("⚠️ WEATHER:", msg.get("summary"), flush=True)

    # -------------------------
    # LEADERBOARD BUILDING
    # -------------------------
    def update_leaderboard(self, city):
        scores = {}

        for model, vals in self.errors[city].items():
            if len(vals) < 3:
                continue

            arr = np.array(vals)
            scores[model] = float(np.mean(arr))

        ranked = sorted(scores.items(), key=lambda x: x[1])

        self.leaderboard[city] = ranked[:5]

        self.print_leaderboard(city)

    # -------------------------
    # OUTPUT
    # -------------------------
    def print_leaderboard(self, city):
        if city not in self.leaderboard:
            return

        print("\n🏆 LEADERBOARD:", city, flush=True)

        for i, (model, score) in enumerate(self.leaderboard[city], 1):
            print(f"{i}. {model} → MAE {score:.3f}", flush=True)

    # -------------------------
    # TICK (safe hook)
    # -------------------------
    def tick(self):
        # placeholder for future summaries
        pass
