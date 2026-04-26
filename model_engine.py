import csv
import time
import os
from collections import defaultdict, deque
import numpy as np

from telegram_alerts import TelegramAlerts


class ModelEngine:
    def __init__(self):
        # =========================
        # HISTORICAL MEMORY
        # =========================
        self.all_errors = defaultdict(list)

        # =========================
        # ROLLING WINDOWS
        # =========================
        self.window_size = 30
        self.rolling_errors = defaultdict(
            lambda: defaultdict(lambda: deque(maxlen=self.window_size))
        )

        # =========================
        # FORECAST MEMORY (TTL)
        # =========================
        self.forecasts = {}
        self.forecast_ttl = 60 * 30

        # =========================
        # ALERT STATE
        # =========================
        self.last_best_by_city = {}
        self.last_alert_time = {}

        self.alert_cooldowns = {
            "HIGH": 120,
            "MEDIUM": 90,
            "LOW": 300
        }

        # =========================
        # DAILY REPORT STATE
        # =========================
        self.last_daily_summary = 0
        self.daily_summary_interval = 60 * 60 * 24

        # =========================
        # METRICS
        # =========================
        self.metrics = {
            "total_forecasts": 0,
            "total_observations": 0,
            "total_errors_logged": 0,
            "model_flips": 0,
            "spikes": 0,
            "low_confidence": 0,
        }

        # =========================
        # TELEGRAM
        # =========================
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
    # EVENT INGESTION
    # =========================================================
    def process_event(self, event):
        if event.get("type") == "forecast":
            self.metrics["total_forecasts"] += 1

            city = event.get("city")
            model = event.get("model")

            if city and model:
                self.forecasts[(city, model)] = {
                    "event": event,
                    "timestamp": time.time()
                }

        elif event.get("type") == "observation":
            self.metrics["total_observations"] += 1
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

            self.metrics["total_errors_logged"] += 1

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
    # PREDICTIVE MODEL (FINAL)
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

        if "Flip" in message:
            self.metrics["model_flips"] += 1
        elif "Spike" in message:
            self.metrics["spikes"] += 1
        elif "Confidence" in message:
            self.metrics["low_confidence"] += 1

    # =========================================================
    # ALERT LOGIC
    # =========================================================
    def detect_alerts(self, city):
        live_best, gap = self.best_model_city(city)
        pred_best = self.predictive_best_model(city)

        prev = self.last_best_by_city.get(city)

        # MODEL FLIP
        if prev and live_best and prev != live_best:
            self.send_alert(
                city,
                "HIGH",
                f"🔁 Model Flip ({city})\n{prev} → {live_best}\nGap: {gap:.2f}"
            )

        self.last_best_by_city[city] = live_best

        # LOW CONFIDENCE
        if gap is not None and gap < 0.5:
            self.send_alert(
                city,
                "LOW",
                f"⚠️ Low Confidence ({city})\nGap: {gap:.2f}"
            )

        # SPIKE
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

        # PREDICTIVE SHIFT
        if pred_best and live_best and pred_best != live_best:
            self.send_alert(
                city,
                "HIGH",
                f"🔮 Forecast Shift ({city})\nLive: {live_best}\nPredicted: {pred_best}"
            )

        # DAILY SUMMARY
        self.run_daily_summary()

    # =========================================================
    # DAILY SUMMARY
    # =========================================================
    def generate_daily_summary(self):
        lines = ["📊 DAILY MODEL SUMMARY\n"]

        for city in self.rolling_errors:
            live_best, _ = self.best_model_city(city)
            pred_best = self.predictive_best_model(city)

            lines.append(f"📍 {city.upper()}")
            lines.append(f"Live: {live_best}")
            lines.append(f"Predicted: {pred_best}\n")

        lines.append("📈 METRICS")
        for k, v in self.metrics.items():
            lines.append(f"{k}: {v}")

        return "\n".join(lines)

    def run_daily_summary(self):
        now = time.time()

        if now - self.last_daily_summary > self.daily_summary_interval:
            msg = self.generate_daily_summary()
            self.telegram.send(msg)
            self.last_daily_summary = now
