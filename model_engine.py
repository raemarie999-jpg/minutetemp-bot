from collections import defaultdict
import numpy as np


class ModelEngine:
    def __init__(self):
        self.errors = defaultdict(list)

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
