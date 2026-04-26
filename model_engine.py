import csv
import time
import os
from collections import defaultdict, deque
import numpy as np

from telegram_alerts import TelegramAlerts


class ModelEngine:
    def __init__(self):
        # -------------------------
        # HISTORICAL DATA
        # -------------------------
        self.all_errors = defaultdict(list)

        # -------------------------
        # ROLLING WINDOW (LIVE)
        # -------------------------
        self.window_size = 30
        self.rolling_errors = defaultdict(
            lambda: defaultdict(lambda: deque(maxlen=self.window_size))
        )

        # -------------------------
        # FORECAST STORAGE (TTL)
        # -------------------------
        self.forecasts = {}
        self.forecast_ttl = 60 * 30  # 30 minutes

        # -------------------------
        # ALERT STATE
        # -------------------------
        self.last_best_by_city = {}
        self.last_alert_time = defaultdict(float)
        self.alert_cooldown = 60

        # -------------------------
        # TELEGRAM
        # -------------------------
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
    # CORE COMPARISON
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

            # store
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
        second = sorted_models[1][1]

        gap = second - sorted_models[0][1]

        return best, gap

    # =========================================================
    # PREDICTIVE BEST MODEL
    # =========================================================
    def predictive_best_model(self, city):
        scores = {}

        for model, errors in self.rolling_errors[city].items():
            if len(errors) < 10:
                continue

            arr = np.array(errors)

            weights = np.linspace(0.5, 1.5, len(arr))
            weighted = np.average(arr, weights=weights)

            stability = np.std(arr)

            scores[model] = weighted + (0.5 * stability)

        if not scores:
            return None

        return min(scores, key=scores.get)

    # =========================================================
    # ALERT ENGINE
    # =========================================================
    def detect_alerts(self, city):
        now = time.time()

        if now - self.last_alert_time[city] < self.alert_cooldown:
            return

        live_best, gap = self.best_model_city(city)
        pred_best = self.predictive_best_model(city)

        prev = self.last_best_by_city.get(city)

        # ---------------- FLIP ----------------
        if prev and live_best and prev != live_best:
            self.telegram.send(
                f"🔁 Model Flip ({city})\n{prev} → {live_best}\nGap: {gap:.2f}"
            )
            self.last_alert_time[city] = now

        self.last_best_by_city[city] = live_best

        # ---------------- CONFIDENCE ----------------
        if gap is not None and gap < 0.5:
            self.telegram.send(
                f"⚠️ Low Confidence ({city})\nGap: {gap:.2f}"
            )
            self.last_alert_time[city] = now

        # ---------------- SPIKE ----------------
        for model, errors in self.rolling_errors[city].items():
            if len(errors) < 10:
                continue

            current = errors[-1]
            baseline = np.mean(list(errors)[:-1])

            if baseline > 0 and current > baseline * 1.5:
                self.telegram.send(
                    f"🚨 Error Spike ({city})\n{model}"
                )
                self.last_alert_time[city] = now

        # ---------------- PREDICTIVE SHIFT ----------------
        if pred_best and live_best and pred_best != live_best:
            self.telegram.send(
                f"🔮 Forecast Shift ({city})\nLive: {live_best}\nPredicted: {pred_best}"
            )
            self.last_alert_time[city] = now
