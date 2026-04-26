import csv
import time
import os
from collections import defaultdict, deque
import numpy as np

from telegram_alerts import TelegramAlerts


class ModelEngine:
    def __init__(self):
        self.rolling_errors = defaultdict(
            lambda: defaultdict(lambda: deque(maxlen=30))
        )

        self.forecasts = {}
        self.forecast_ttl = 60 * 30

        self.last_best_by_city = {}
        self.last_alert_time = {}

        self.telegram = TelegramAlerts()

        self.alert_cooldowns = {
            "HIGH": 120,
            "MEDIUM": 90,
            "LOW": 300
        }

        self.last_daily_summary = 0
        self.daily_summary_interval = 60 * 60 * 24

        self.metrics = {
            "forecasts": 0,
            "observations": 0,
            "errors": 0,
            "flips": 0,
            "spikes": 0,
            "low_conf": 0,
        }

    # -------------------------
    # EVENT INGESTION
    # -------------------------
    def process_event(self, event):
        if event.get("type") == "forecast":
            self.metrics["forecasts"] += 1

            city = event.get("city")
            model = event.get("model")

            if city and model:
                self.forecasts[(city, model)] = {
                    "event": event,
                    "ts": time.time()
                }

        elif event.get("type") == "observation":
            self.metrics["observations"] += 1
            self.compare(event)

    # -------------------------
    # CORE LOGIC
    # -------------------------
    def compare(self, obs):
        city = obs.get("city")
        actual = obs.get("value")

        if not city:
            return

        now = time.time()

        for (c, model), data in self.forecasts.items():
            if c != city:
                continue

            if now - data["ts"] > self.forecast_ttl:
                continue

            predicted = data["event"].get("value")
            if predicted is None:
                continue

            error = abs(predicted - actual)

            self.rolling_errors[city][model].append(error)
            self.metrics["errors"] += 1

        self.detect_alerts(city)

    # -------------------------
    # BEST MODEL
    # -------------------------
    def best_model_city(self, city):
        scores = {
            m: np.mean(v)
            for m, v in self.rolling_errors[city].items()
            if len(v) >= 5
        }

        if len(scores) < 2:
            return None, None

        sorted_models = sorted(scores.items(), key=lambda x: x[1])

        return sorted_models[0][0], (
            sorted_models[1][1] - sorted_models[0][1]
        )

    # -------------------------
    # PREDICTIVE MODEL
    # -------------------------
    def predictive_best_model(self, city):
        scores = {}

        for model, errors in self.rolling_errors[city].items():
            if len(errors) < 10:
                continue

            arr = np.array(errors)

            weighted = np.average(arr, weights=np.linspace(0.5, 1.5, len(arr)))
            slope = np.polyfit(np.arange(len(arr)), arr, 1)[0]
            vol = np.std(arr)

            scores[model] = weighted + 0.8 * slope + 0.5 * vol

        return min(scores, key=scores.get) if scores else None

    # -------------------------
    # ALERT SYSTEM
    # -------------------------
    def send_alert(self, city, level, msg):
        now = time.time()
        key = (city, level)

        if now - self.last_alert_time.get(key, 0) < self.alert_cooldowns[level]:
            return

        self.last_alert_time[key] = now
        self.telegram.send(msg)

    # -------------------------
    # ALERT LOGIC
    # -------------------------
    def detect_alerts(self, city):
        live_best, gap = self.best_model_city(city)
        pred_best = self.predictive_best_model(city)

        prev = self.last_best_by_city.get(city)

        if prev and live_best and prev != live_best:
            self.metrics["flips"] += 1
            self.send_alert(city, "HIGH", f"🔁 Flip {city}: {prev} → {live_best}")

        if gap is not None and gap < 0.5:
            self.metrics["low_conf"] += 1
            self.send_alert(city, "LOW", f"⚠️ Low confidence {city}")

        if pred_best and live_best and pred_best != live_best:
            self.send_alert(city, "HIGH", f"🔮 Shift {city}: {pred_best} → {live_best}")

        self.last_best_by_city[city] = live_best

    # -------------------------
    # DAILY SUMMARY
    # -------------------------
    def daily_summary(self):
        lines = ["📊 DAILY SUMMARY"]

        for k, v in self.metrics.items():
            lines.append(f"{k}: {v}")

        return "\n".join(lines)
