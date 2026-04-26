import csv
import time
import os
from collections import defaultdict
import numpy as np


class ModelEngine:
    def __init__(self):
        self.errors = defaultdict(list)

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

    def process_event(self, event):
        if event.get("type") == "forecast":
            self.forecast = event

        if event.get("type") == "observation":
            self.compare(event)

    def compare(self, obs):
        city = obs.get("city")
        actual = obs.get("value")

        if not hasattr(self, "forecast"):
            return

        f = self.forecast

        if f.get("city") != city:
            return

        model = f.get("model")
        predicted = f.get("value")

        error = abs(predicted - actual)

        self.errors[model].append(error)

    def best_model(self):
        scores = {
            m: np.mean(v)
            for m, v in self.errors.items()
            if len(v) > 0
        }

        if not scores:
            return None

        return min(scores, key=scores.get)
