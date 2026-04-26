import csv
import time
import os
from collections import defaultdict, deque
import numpy as np


class ModelEngine:
    def __init__(self):
        # -------------------------
        # HISTORICAL MEMORY
        # -------------------------
        self.all_errors = defaultdict(list)

        # -------------------------
        # ACTIVE ROLLING WINDOWS
        # -------------------------
        self.window_size = 30
        self.rolling_errors = defaultdict(lambda: defaultdict(lambda: deque(maxlen=self.window_size)))

        # -------------------------
        # FORECAST STORAGE (with TTL)
        # -------------------------
        self.forecasts = {}
        self.forecast_ttl = 60 * 30  # 30 minutes

        # -------------------------
        # ALERT STATE
        # -------------------------
        self.last_best_by_city = {}
        self.last_alert_time = defaultdict(float)
        self.alert_cooldown = 60  # seconds

    # =========================================================
    # CSV LOGGING (HISTORICAL — NEVER FILTERED)
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
    # CORE COMPARISON ENGINE
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

            # -------------------------
            # TTL FILTER (ACTIVE WINDOW)
            # -------------------------
            if now - data["timestamp"] > self.forecast_ttl:
                continue

            f = data["event"]

            predicted = f.get("value")
            if predicted is None:
                continue

            error = abs(predicted - actual)

            # -------------------------
            # STORE HISTORICAL + ROLLING
            # -------------------------
            self.all_errors[model].append(error)
            self.rolling_errors[city][model].append(error)

            self.log_row(city, model, predicted, actual, error)

        # -------------------------
        # RUN ALERTS
        # -------------------------
        self.detect_alerts(city)

    # =========================================================
    # GLOBAL BEST MODEL (HISTORICAL)
    # =========================================================
    def best_model(self):
        scores = {
            m: np.mean(v)
            for m, v in self.all_errors.items()
            if len(v) > 0
        }

        if not scores:
            return None

        return min(scores, key=scores.get)

    # =========================================================
    # CITY BEST MODEL (ROLLING = LIVE INTELLIGENCE)
    # =========================================================
    def best_model_city(self, city):
        scores = {
            m: np.mean(v)
            for m, v in self.rolling_errors[city].items()
            if len(v) >= 5  # stability requirement
        }

        if len(scores) < 2:
            return None, None

        sorted_models = sorted(scores.items(), key=lambda x: x[1])

        best_model, best_score = sorted_models[0]
        second_score = sorted_models[1][1]

        confidence_gap = second_score - best_score

        return best_model, confidence_gap

    # =========================================================
    # TRUE PREDICTIVE BEST MODEL
    # (trend-weighted, not just raw mean)
    # =========================================================
    def predictive_best_model(self, city):
        weighted_scores = {}

        for model, errors in self.rolling_errors[city].items():
            if len(errors) < 10:
                continue

            arr = np.array(errors)

            # recent performance weighted more heavily
            weights = np.linspace(0.5, 1.5, len(arr))
            weighted_avg = np.average(arr, weights=weights)

            # stability penalty (variance)
            stability = np.std(arr)

            score = weighted_avg + (0.5 * stability)

            weighted_scores[model] = score

        if not weighted_scores:
            return None

        return min(weighted_scores, key=weighted_scores.get)

    # =========================================================
    # ALERT SYSTEM
    # =========================================================
    def detect_alerts(self, city):
        best_live, confidence_gap = self.best_model_city(city)
        best_predicted = self.predictive_best_model(city)

        now = time.time()

        # cooldown protection
        if now - self.last_alert_time[city] < self.alert_cooldown:
            return

        # -------------------------
        # MODEL FLIP ALERT
        # -------------------------
        prev = self.last_best_by_city.get(city)

        if prev and best_live and prev != best_live:
            print(f"🔁 MODEL FLIP [{city}] {prev} → {best_live}")
            self.last_alert_time[city] = now

        self.last_best_by_city[city] = best_live

        # -------------------------
        # CONFIDENCE ALERT
        # -------------------------
        if confidence_gap is not None and confidence_gap < 0.5:
            print(f"⚠️ LOW CONFIDENCE [{city}] gap={confidence_gap:.3f}")
            self.last_alert_time[city] = now

        # -------------------------
        # ERROR SPIKE ALERT
        # -------------------------
        for model, errors in self.rolling_errors[city].items():
            if len(errors) < 10:
                continue

            current = errors[-1]
            baseline = np.mean(list(errors)[:-1])

            if baseline > 0 and current > baseline * 1.5:
                print(f"🚨 ERROR SPIKE [{city}] {model}")
                self.last_alert_time[city] = now
