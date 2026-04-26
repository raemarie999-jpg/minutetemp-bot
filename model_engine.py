import csv
import time
import os
from collections import defaultdict, deque
import numpy as np

from telegram_alerts import TelegramAlerts


class ModelEngine:
    def __init__(self):
        # ----------------------------
        # HISTORICAL STORAGE
        # ----------------------------
        self.all_errors = defaultdict(list)

        # ----------------------------
        # ROLLING WINDOWS
        # ----------------------------
        self.window_size = 30
        self.rolling_errors = defaultdict(
            lambda: defaultdict(lambda: deque(maxlen=self.window_size))
        )

        # ----------------------------
        # FORECAST STORAGE (TTL)
        # ----------------------------
        self.forecasts = {}
        self.forecast_ttl = 60 * 30  # 30 min

        # ----------------------------
        # ALERT STATE
        # ----------------------------
        self.last_best_by_city = {}
        self.last_alert_time = {}
        self.alert_cooldowns = {
            "HIGH": 120,
            "MEDIUM": 90,
            "LOW": 300
        }

        # ----------------------------
        # TELEGRAM
        # ----------------------------
        self.telegram = TelegramAlerts()

    # =========================================================
    # LOGGING
    # =========================================================
    def log_row(self, city, model, predicted, actual, error):
        file_exists = os.path.isfile("model_log.csv")

        with open("model_log.csv", "a", newline="") as f:
            writer = csv.writer(f)

            if not file_exists:
                writer.writerow(["timestamp", "city", "model", "predicted", "actual", "error"])

            writer.writerow([
                time.time(),
                city,
                model,
                predicted,
                actual,
                error
            ])

    # =========================================================
    # INGESTION
    # =========================================================
    def process_event(self, event):
        if event.get("type") == "forecast":
            city = event.get("city")
            model = event.get("model")

            if city and model:
                self.forecasts[(city, model)] = {
                    "event": event,
                    "timestamp": time.time()
                }

        elif event.get("type") == "observation":
            self.compare(event)

    # =========================================================
    # CORE ENGINE
    # =========================================================
    def compare(self, obs):
        city = obs.get("city")
        actual = obs.get("value")

        if not city:
            return

        now = time.time()

        for (c, model), data in self.forecasts.items():
            if c != city:
                continue

            if now - data["timestamp"] > self.forecast_ttl:
                continue

            f = data["event"]
            predicted = f.get("value")

            if predicted is None:
                continue

            error = abs(predicted - actual)

            self.all_errors[model].append(error)
            self.rolling_errors[city][model].append(error)

            self.log_row(city, model, predicted, actual, error)

        self.detect_alerts(city)

    # =========================================================
    # LIVE BEST MODEL
    # =========================================================
    def best_model_city(self, city):
        scores = {
            m: np.mean(v)
            for m, v in self.rolling_errors[city].items()
            if len(v) >= 5
        }

        if len(scores) < 2:
            return None, None

        sorted_models = sorted(scores.items(), key=lambda x: x[1])

        best = sorted_models[0][0]
        gap = sorted_models[1][1] - sorted_models[0][1]

        return best, gap

    # =========================================================
    # PREDICTIVE MODEL (UPGRADED)
    # =========================================================
    def predictive_best_model(self, city):
        scores = {}

        for model, errors in self.rolling_errors[city].items():
            if len(errors) < 10:
                continue

            arr = np.array(errors)

            weights = np.linspace(0.5, 1.5, len(arr))
            weighted_mean = np.average(arr, weights=weights)

            slope = np.polyfit(np.arange(len(arr)), arr, 1)[0]

            volatility = np.std(arr)

            score = weighted_mean + (0.8 * slope) + (0.5 * volatility)

            scores[model] = score

        if not scores:
            return None

        return min(scores, key=scores.get)

    # =========================================================
    # ALERT SYSTEM
    # =========================================================
    def send_alert(self, city, level, message):
        now = time.time()

        key = (city, level)
        cooldown = self.alert_cooldowns.get(level, 60)

        if now - self.last_alert_time.get(key, 0) < cooldown:
            return

        self.last_alert_time[key] = now
        self.telegram.send(message)

    # =========================================================
    # ALERT LOGIC
    # =========================================================
    def detect_alerts(self, city):
        live_best, gap = self.best_model_city(city)
        pred_best = self.predictive_best_model(city)

        prev = self.last_best_by_city.get(city)

        # ---------------- FLIP ----------------
        if prev and live_best and prev != live_best:
            self.send_alert(
                city,
                "HIGH",
                f"🔁 Model Flip ({city})\n{prev} → {live_best}\nGap: {gap:.2f}"
            )

        self.last_best_by_city[city] = live_best

        # ---------------- CONFIDENCE ----------------
        if gap is not None and gap < 0.5:
            self.send_alert(
                city,
                "LOW",
                f"⚠️ Low Confidence ({city})\nGap: {gap:.2f}"
            )

        # ---------------- SPIKE ----------------
        for model, errors in self.rolling_errors[city].items():
            if len(errors) < 10:
                continue

            current = errors[-1]
            baseline = np.mean(list(errors)[:-1])

            if baseline > 0 and current > baseline * 1.5:
                self.send_alert(
                    city,
                    "MEDIUM",
                    f"🚨 Error Spike ({city})\n{model}"
                )

        # ---------------- PREDICTIVE SHIFT ----------------
        if pred_best and live_best and pred_best != live_best:
            self.send_alert(
                city,
                "HIGH",
                f"🔮 Forecast Shift ({city})\nLive: {live_best}\nPredicted: {pred_best}"
            )
