import csv
import time
import os
from collections import defaultdict
import numpy as np


class ModelEngine:
    def __init__(self):
        self.errors = defaultdict(list)
        self.errors_by_city = defaultdict(lambda: defaultdict(list))
        self.forecasts = {}

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
            city = event.get("city")
            if city is not None:
                self.forecasts[city] = event

        if event.get("type") == "observation":
            self.compare(event)

    def compare(self, obs):
        city = obs.get("city")
        actual = obs.get("value")

        f = self.forecasts.get(city)
        if f is None:
            return

        model = f.get("model")
        predicted = f.get("value")

        error = abs(predicted - actual)

        self.errors[model].append(error)
        self.errors_by_city[city][model].append(error)

        self.log_row(city, model, predicted, actual, error)

    def best_model(self):
        scores = {
            m: np.mean(v)
            for m, v in self.errors.items()
            if len(v) > 0
        }

        if not scores:
            return None

        return min(scores, key=scores.get)

    def leaderboard(self):
        rows = [
            (m, float(np.mean(v)), len(v))
            for m, v in self.errors.items()
            if len(v) > 0
        ]

        rows.sort(key=lambda r: r[1])

        return rows

    def best_model_for_city(self, city):
        scores = {
            m: np.mean(v)
            for m, v in self.errors_by_city.get(city, {}).items()
            if len(v) > 0
        }

        if not scores:
            return None

        return min(scores, key=scores.get)

    def leaderboard_by_city(self):
        result = {}

        for city, models in self.errors_by_city.items():
            rows = [
                (m, float(np.mean(v)), len(v))
                for m, v in models.items()
                if len(v) > 0
            ]
            rows.sort(key=lambda r: r[1])
            result[city] = rows

        return result

    def model_wins(self):
        wins = defaultdict(int)

        for city in self.errors_by_city:
            best = self.best_model_for_city(city)
            if best is not None:
                wins[best] += 1

        def sort_key(item):
            model, count = item
            overall = self.errors.get(model, [])
            avg = float(np.mean(overall)) if overall else float("inf")
            return (-count, avg)

        rows = sorted(wins.items(), key=sort_key)

        return rows

    def snapshot_leaderboard(self, path="leaderboard.csv"):
        by_city = self.leaderboard_by_city()
        if not by_city:
            return

        file_exists = os.path.isfile(path)
        ts = time.time()

        with open(path, "a", newline="") as f:
            writer = csv.writer(f)

            if not file_exists:
                writer.writerow(["timestamp", "city", "model", "avg_error", "samples"])

            for city, rows in by_city.items():
                for model, avg_error, samples in rows:
                    writer.writerow([ts, city, model, avg_error, samples])
