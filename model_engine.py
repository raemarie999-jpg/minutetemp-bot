import time
from collections import defaultdict, deque
from datetime import datetime, timezone

import numpy as np

from telegram_alerts import TelegramAlerts


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ModelEngine:
    def __init__(self):
        # oracle history
        self.oracle_errors = defaultdict(lambda: defaultdict(lambda: deque(maxlen=50)))

        # live data
        self.latest_forecasts = defaultdict(dict)   # city -> model -> value
        self.latest_observation = {}

        # state
        self.current_best = {}
        self.last_alert_time = {}

        self.telegram = TelegramAlerts()

        self.cooldowns = {
            "CHANGE": 120,
            "WEAK": 300,
        }

        self.mode_weights = {
            "day_of": 1.5,
            "day_ahead": 1.2,
            "overall": 1.0,
        }

    # -------------------------
    # ENTRY
    # -------------------------
    def process_event(self, event):
        etype = event.get("type")

        if etype == "oracle_scores":
            self._handle_oracle(event)

        elif etype == "forecast":
            self._handle_forecast(event)

        elif etype == "observation":
            self._handle_observation(event)

    # -------------------------
    # ORACLE SCORES
    # -------------------------
    def _handle_oracle(self, event):
        city = event.get("city")
        scores = event.get("scores") or []
        mode = event.get("mode", "overall")

        if not city:
            return

        weight = self.mode_weights.get(mode, 1.0)

        for s in scores:
            model = s.get("model_id")
            mae = s.get("combined_mae")

            if model is None or mae is None:
                continue

            try:
                mae = float(mae)
            except:
                continue

            self.oracle_errors[city][model].append(mae * weight)

        self._evaluate(city)

    # -------------------------
    # FORECASTS
    # -------------------------
    def _handle_forecast(self, event):
        city = event.get("city")
        models = event.get("models") or []

        if not city:
            return

        for m in models:
            model_id = m.get("model_id")
            value = m.get("value") or m.get("prediction")

            if model_id is None or value is None:
                continue

            try:
                self.latest_forecasts[city][model_id] = float(value)
            except:
                continue

    # -------------------------
    # OBSERVATIONS
    # -------------------------
    def _handle_observation(self, event):
        city = event.get("city")
        value = event.get("value")

        if city is None or value is None:
            return

        try:
            self.latest_observation[city] = float(value)
        except:
            return

        self._evaluate(city)

    # -------------------------
    # CORE EVALUATION
    # -------------------------
    def _evaluate(self, city):
        obs = self.latest_observation.get(city)

        model_scores = {}

        # -------------------------
        # SCORE EACH MODEL
        # -------------------------
        for model, hist in self.oracle_errors[city].items():
            if len(hist) < 5:
                continue

            arr = np.array(hist)

            oracle_mean = np.mean(arr)
            trend = np.polyfit(range(len(arr)), arr, 1)[0]
            vol = np.std(arr)

            base = oracle_mean + 0.7 * trend + 0.5 * vol

            # live adjustment
            live_penalty = 0

            forecast = self.latest_forecasts[city].get(model)

            if obs is not None and forecast is not None:
                live_error = abs(forecast - obs)
                live_penalty = live_error * 1.5

            model_scores[model] = base + live_penalty

        if len(model_scores) < 2:
            return

        ranked = sorted(model_scores.items(), key=lambda x: x[1])

        best_score = ranked[0][1]
        second_score = ranked[1][1]

        gap = second_score - best_score

        # -------------------------
        # CONFIDENCE SCORE
        # -------------------------
        # bigger gap + lower volatility = higher confidence
        confidence = min(100, max(0, int(
            (gap * 120)
        )))

        # -------------------------
        # OUTPUT RANKING
        # -------------------------
        print(f"\n🏙 {city.upper()} MODEL RANKING")

        for i, (model, score) in enumerate(ranked[:5], 1):
            label = ""
            if i == 1:
                label = f"  ← BEST (conf {confidence})"
            print(f"{i}) {model} — {score:.3f}{label}")

        # -------------------------
        # ALERT LOGIC
        # -------------------------
        best_model = ranked[0][0]
        prev_best = self.current_best.get(city)

        if prev_best and prev_best != best_model:
            self._alert(city, "CHANGE",
                        f"🔁 {city.upper()} flip: {prev_best} → {best_model}")

        if confidence < 25:
            self._alert(city, "WEAK",
                        f"⚠️ {city.upper()} low confidence ({confidence})")

        self.current_best[city] = best_model

    # -------------------------
    # ALERT SYSTEM
    # -------------------------
    def _alert(self, city, level, msg):
        now_ts = time.time()
        key = (city, level)

        if now_ts - self.last_alert_time.get(key, 0) < self.cooldowns[level]:
            return

        self.last_alert_time[key] = now_ts

        print(f"🚨 ALERT: {msg}", flush=True)
        self.telegram.send(msg)

    # -------------------------
    # OPTIONAL SUMMARY
    # -------------------------
    def maybe_send_daily_summary(self):
        pass
