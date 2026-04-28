import numpy as np
from collections import defaultdict, deque
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ModelEngineV2:
    """
    Live forecasting decision engine:
    - tracks model forecasts
    - compares to observations
    - integrates oracle scores
    - produces ranked leaderboard per city
    """

    def __init__(self):
        # city -> model -> latest forecast
        self.forecasts = defaultdict(dict)

        # city -> latest observation
        self.observations = {}

        # city -> model -> rolling forecast errors
        self.errors = defaultdict(lambda: defaultdict(lambda: deque(maxlen=50)))

        # oracle skill store:
        # city -> model -> {"overall": x, "day_ahead": y}
        self.oracle = defaultdict(lambda: defaultdict(dict))

    # -------------------------
    # EVENT ENTRY POINT
    # -------------------------
    def process_event(self, event):
        etype = event.get("type")

        if etype == "observation":
            self._handle_observation(event)

        elif etype == "forecast":
            self._handle_forecast(event)

        elif etype == "oracle_scores":
            self._handle_oracle(event)

    # -------------------------
    # OBSERVATION (TRUTH)
    # -------------------------
    def _handle_observation(self, event):
        city = event["city"]
        value = event["value"]

        self.observations[city] = float(value)

        # score all forecasts against truth
        self._update_errors(city)

    # -------------------------
    # FORECASTS (MODEL OUTPUTS)
    # -------------------------
    def _handle_forecast(self, event):
        city = event["city"]
        models = event.get("models", [])

        for m in models:
            model = m.get("model_id")
            value = m.get("value")

            if model is None or value is None:
                continue

            self.forecasts[city][model] = float(value)

    # -------------------------
    # ORACLE SCORES (MODEL HISTORY)
    # -------------------------
    def _handle_oracle(self, event):
        city = event["city"]
        scores = event.get("scores", [])

        for s in scores:
            model = s.get("model_id")
            if not model:
                continue

            self.oracle[city][model] = {
                "overall": float(s.get("overall_mae", 1.0)),
                "day_ahead": float(s.get("day_ahead_mae", 1.0)),
            }

    # -------------------------
    # ERROR UPDATE
    # -------------------------
    def _update_errors(self, city):
        if city not in self.observations:
            return

        obs = self.observations[city]

        for model, pred in self.forecasts[city].items():
            err = abs(pred - obs)
            self.errors[city][model].append(err)

    # -------------------------
    # WEIGHTED MODEL SCORE
    # -------------------------
    def _model_score(self, city, model):
        errs = self.errors[city][model]
        if len(errs) < 3:
            return None

        # recent performance
        recent = np.mean(errs)

        # oracle weighting (if available)
        oracle = self.oracle[city].get(model, {})
        overall = oracle.get("overall", 1.0)
        day_ahead = oracle.get("day_ahead", 1.0)

        oracle_weight = 0.6 * day_ahead + 0.4 * overall

        return 0.7 * recent + 0.3 * oracle_weight

    # -------------------------
    # TREND DETECTION
    # -------------------------
    def _trend(self, city, model):
        errs = self.errors[city][model]
        if len(errs) < 6:
            return "stable"

        x = np.arange(len(errs))
        slope = np.polyfit(x, errs, 1)[0]

        if slope < -0.01:
            return "improving"
        elif slope > 0.01:
            return "worsening"
        return "stable"

    # -------------------------
    # LEADERBOARD
    # -------------------------
    def get_leaderboard(self, city):
        scores = {}

        for model in self.forecasts[city].keys():
            score = self._model_score(city, model)
            if score is None:
                continue

            scores[model] = score

        ranked = sorted(scores.items(), key=lambda x: x[1])

        return ranked[:5]

    # -------------------------
    # DASHBOARD OUTPUT
    # -------------------------
    def print_dashboard(self):
        for city in self.observations.keys():
            print("\n" + "=" * 60)
            print(f"🏙 CITY: {city.upper()}")

            leaderboard = self.get_leaderboard(city)

            if not leaderboard:
                print("No usable model data yet.")
                continue

            print("\n🏆 MODEL LEADERBOARD (Top 5)\n")

            for i, (model, score) in enumerate(leaderboard, 1):
                trend = self._trend(city, model)

                arrow = {
                    "improving": "📉 improving",
                    "worsening": "📈 worsening",
                    "stable": "➡️ stable",
                }[trend]

                print(f"{i}. {model:<8} score={score:.3f} {arrow}")

            best = leaderboard[0][1]
            second = leaderboard[1][1] if len(leaderboard) > 1 else best

            spread = second - best

            if spread < 0.2:
                conf = "LOW CONFIDENCE ⚠️"
            elif spread < 0.5:
                conf = "MEDIUM CONFIDENCE"
            else:
                conf = "HIGH CONFIDENCE ✅"

            print("\n⚖️", conf)
