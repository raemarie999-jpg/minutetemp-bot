import csv
import os
import time
from collections import defaultdict, deque
from datetime import datetime, timezone

import numpy as np

from telegram_alerts import TelegramAlerts


LOG_DIR = os.getenv(
    "WORKER_LOG_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs"),
)


# -------------------------
# UTIL
# -------------------------
def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# -------------------------
# CSV LOGGER
# -------------------------
class CsvLogger:
    def __init__(self, path, header):
        self.path = path
        self.header = header
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._ensure_header()

    def _ensure_header(self):
        if not os.path.exists(self.path) or os.path.getsize(self.path) == 0:
            with open(self.path, "w", newline="") as f:
                csv.writer(f).writerow(self.header)

    def write(self, row):
        try:
            self._ensure_header()
            with open(self.path, "a", newline="") as f:
                csv.writer(f).writerow(row)
        except Exception as e:
            print("⚠️ CSV write error:", repr(e), flush=True)


# -------------------------
# MODEL ENGINE
# -------------------------
class ModelEngine:
    def __init__(self):
        self.telegram = TelegramAlerts()

        # city -> model -> deque(errors)
        self.errors = defaultdict(lambda: defaultdict(lambda: deque(maxlen=50)))

        # last alert timestamps
        self.last_alert_time = {}

        # last best model (for flip detection)
        self.last_best = {}

        # logs
        self.obs_log = CsvLogger(
            os.path.join(LOG_DIR, "observations.csv"),
            ["ts", "city", "station", "temp"],
        )

        self.score_log = CsvLogger(
            os.path.join(LOG_DIR, "scores.csv"),
            ["ts", "city", "model", "mae"],
        )

        self.decision_log = CsvLogger(
            os.path.join(LOG_DIR, "decisions.csv"),
            ["ts", "city", "best_model", "score"],
        )

        print("🧠 ModelEngine initialized", flush=True)

    # -------------------------
    # EVENT ENTRYPOINT
    # -------------------------
    def process_event(self, event):
        t = event.get("type")

        if t == "observation":
            self._handle_observation(event)

        elif t == "oracle_scores":
            self._handle_scores(event)

    # -------------------------
    # OBSERVATIONS
    # -------------------------
    def _handle_observation(self, e):
        city = e.get("city")
        temp = e.get("value")
        station = e.get("station_id")

        if city and temp is not None:
            self.obs_log.write([_now_iso(), city, station, temp])

    # -------------------------
    # ORACLE SCORES (CORE)
    # -------------------------
    def _handle_scores(self, e):
        city = e.get("city")
        scores = e.get("scores") or []

        if not city:
            return

        for s in scores:
            model = s.get("model_id")
            mae = s.get("combined_mae")

            if model is None or mae is None:
                continue

            try:
                mae = float(mae)
            except:
                continue

            self.errors[city][model].append(mae)
            self.score_log.write([_now_iso(), city, model, mae])

        # 🔥 After updating scores → recompute best model
        self.evaluate_city(city)

    # -------------------------
    # CORE SCORING LOGIC
    # -------------------------
    def score_model(self, errors):
        """
        Combine:
        - weighted MAE (recent matters more)
        - trend (getting better/worse)
        - volatility (penalize unstable models)
        """

        if len(errors) < 5:
            return None

        arr = np.array(errors)

        # recent weighting
        weights = np.linspace(0.5, 1.5, len(arr))
        weighted_mae = np.average(arr, weights=weights)

        # trend (slope)
        slope = np.polyfit(np.arange(len(arr)), arr, 1)[0]

        # volatility
        volatility = np.std(arr)

        # final score (lower is better)
        return weighted_mae + (0.7 * slope) + (0.5 * volatility)

    # -------------------------
    # EVALUATE BEST MODEL
    # -------------------------
    def evaluate_city(self, city):
        models = self.errors[city]

        scores = {}

        for model, errs in models.items():
            score = self.score_model(errs)
            if score is not None:
                scores[model] = score

        if len(scores) < 2:
            return

        best = min(scores, key=scores.get)
        best_score = scores[best]

        self.decision_log.write([
            _now_iso(),
            city,
            best,
            best_score,
        ])

        print(f"🏆 BEST MODEL {city}: {best} ({best_score:.3f})", flush=True)

        self._maybe_alert(city, best, best_score)

    # -------------------------
    # ALERT LOGIC
    # -------------------------
    def _maybe_alert(self, city, best, score):
        prev = self.last_best.get(city)
        now = time.time()

        cooldown = 120

        if prev and prev != best:
            key = f"{city}_flip"

            if now - self.last_alert_time.get(key, 0) > cooldown:
                self.last_alert_time[key] = now

                msg = f"🔁 {city.upper()} model flip: {prev} → {best}"
                print("🚨", msg, flush=True)
                self.telegram.send(msg)

        self.last_best[city] = best

    # -------------------------
    # DAILY SUMMARY (optional)
    # -------------------------
    def maybe_send_daily_summary(self):
        pass
