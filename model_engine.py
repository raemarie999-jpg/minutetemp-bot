import csv
import time
import os
from collections import defaultdict, deque
import numpy as np


class ModelEngine:
    def __init__(self):
        # raw error history (full)
        self.errors = defaultdict(list)

        # rolling windows (last N errors)
        self.window_size = 30
        self.rolling_errors = defaultdict(lambda: defaultdict(lambda: deque(maxlen=self.window_size)))

        # forecasts cache
        self.forecasts = {}

        # tracking state
        self.last_best_by_city = {}
        self.last_alert_time = defaultdict(float)

    # ----------------------------
    # CSV LOGGING
    # ----------------------------
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

    # ----------------------------
    # EVENT HANDLING
    # ----------------------------
    def process_event(self, event):
        if event.get("type") == "forecast":
            city = event.get("city")
            model = event.get("model")

            if city and model:
                self.forecasts[(city, model)] = event

        if event.get("type") == "observation":
            self.compare(event)

    # ----------------------------
    # CORE COMPARISON
    # ----------------------------
    def compare(self, obs):
        city = obs.get("city")
        actual = obs.get("value")

        if not city:
            return

        # compare ALL models for this city
        for (c, model), f in self.forecasts.items():
            if c != city:
                continue

            predicted = f.get("value")
            error = abs(predicted - actual)

            # store errors
            self.errors[model].append(error)
            self.rolling_errors[city][model].append(error)

            self.log_row(city, model, predicted, actual, error)

        # run alerts after update
        self.detect_alerts(city)

    # ----------------------------
    # BEST MODEL (GLOBAL)
    # ----------------------------
    def best_model(self):
        scores = {
            m: np.mean(v)
            for m, v in self.errors.items()
            if len(v) > 0
        }

        if not scores:
            return None

        return min(scores, key=scores.get)

    # ----------------------------
    # BEST MODEL PER CITY (rolling)
    # ----------------------------
    def best_model_city(self, city):
        scores = {
            m: np.mean(v)
            for m, v in self.rolling_errors[city].items()
            if len(v) > 0
        }

        if not scores:
            return None, None

        sorted_models = sorted(scores.items(), key=lambda x: x[1])

        best = sorted_models[0][0]
        best_score = sorted_models[0][1]

        second_score = sorted_models[1][1] if len(sorted_models) > 1 else best_score

        confidence_gap = second_score - best_score

        return best, confidence_gap

    # ----------------------------
    # ALERT ENGINE
    # ----------------------------
    def detect_alerts(self, city):
        best, confidence_gap = self.best_model_city(city)

        if not best:
            return

        prev_best = self.last_best_by_city.get(city)

        # 1. MODEL FLIP
        if prev_best and prev_best != best:
            print(f"🔁 MODEL FLIP [{city}]: {prev_best} → {best}")

        self.last_best_by_city[city] = best

        # 2. CONFIDENCE ALERT
        if confidence_gap < 0.5:
            print(f"⚠️ LOW CONFIDENCE [{city}] gap={confidence_gap:.3f}")

        # 3. ERROR SPIKE
        for model, errors in self.rolling_errors[city].items():
            if len(errors) < 5:
                continue

            current = errors[-1]
            baseline = np.mean(list(errors)[:-1])

            if baseline > 0 and current > baseline * 1.5:
                print(f"🚨 ERROR SPIKE [{city}] {model}: {current:.2f} vs {baseline:.2f}")
