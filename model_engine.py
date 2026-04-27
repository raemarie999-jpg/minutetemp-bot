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


# =========================
# CSV LOGGER
# =========================
class CsvLogger:
    def __init__(self, path: str, header: list):
        self.path = path
        self.header = header
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._ensure_header()

    def _ensure_header(self):
        if not os.path.exists(self.path) or os.path.getsize(self.path) == 0:
            with open(self.path, "w", newline="") as f:
                csv.writer(f).writerow(self.header)

    def write(self, row: list):
        try:
            self._ensure_header()
            with open(self.path, "a", newline="") as f:
                csv.writer(f).writerow(row)
        except Exception as e:
            print(f"⚠️ CSV write error ({self.path}):", repr(e), flush=True)


def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# =========================
# MODEL ENGINE
# =========================
class ModelEngine:
    def __init__(self):
        # city -> mode -> model -> deque(errors)
        self.rolling_errors = defaultdict(
            lambda: defaultdict(lambda: defaultdict(lambda: deque(maxlen=30)))
        )

        self.last_best_by_city = {}
        self.last_alert_time = {}

        self.telegram = TelegramAlerts()

        self.alert_cooldowns = {
            "HIGH": 120,
            "MEDIUM": 90,
            "LOW": 300,
        }

        self.last_daily_summary = 0
        self.daily_summary_interval = 86400

        self.metrics = {
            "observations": 0,
            "errors": 0,
            "flips": 0,
            "low_conf": 0,
        }

        # logs
        self.obs_log = CsvLogger(
            os.path.join(LOG_DIR, "observations.csv"),
            ["ts", "city", "station_id", "value"],
        )

        self.scores_log = CsvLogger(
            os.path.join(LOG_DIR, "scores.csv"),
            [
                "ts", "city", "station_id", "mode",
                "model_id", "model_name", "combined_mae"
            ],
        )

        self.decision_log = CsvLogger(
            os.path.join(LOG_DIR, "decisions.csv"),
            ["ts", "city", "best_model", "score_gap"],
        )

        self.alert_log = CsvLogger(
            os.path.join(LOG_DIR, "alerts.csv"),
            ["ts", "city", "level", "message", "sent"],
        )

    # =========================
    # EVENT INGESTION
    # =========================
    def process_event(self, event):
        etype = event.get("type")

        if etype == "observation":
            self.metrics["observations"] += 1

            self.obs_log.write([
                _now_iso(),
                event.get("city"),
                event.get("station_id"),
                event.get("value"),
            ])

        elif etype == "oracle_scores":
            self.process_oracle_scores(event)

    # =========================
    # STORE SCORES (MULTI-MODE)
    # =========================
    def process_oracle_scores(self, event):
        city = event.get("city")
        mode = event.get("mode")
        scores = event.get("scores") or []

        if not city or not mode:
            return

        for s in scores:
            model_id = s.get("model_id")
            mae = s.get("combined_mae")

            if model_id is None or mae is None:
                continue

            try:
                mae = float(mae)
            except:
                continue

            self.rolling_errors[city][mode][model_id].append(mae)
            self.metrics["errors"] += 1

            self.scores_log.write([
                _now_iso(),
                city,
                event.get("station_id"),
                mode,
                model_id,
                s.get("model_name"),
                mae,
            ])

    # =========================
    # COMBINED MODEL SCORE
    # =========================
    def compute_weighted_scores(self, city):
        weights = {
            "overall": 0.2,
            "day_ahead": 0.3,
            "day_of": 0.5,
        }

        model_scores = defaultdict(float)
        model_counts = defaultdict(int)

        for mode, w in weights.items():
            for model, errors in self.rolling_errors[city][mode].items():
                if len(errors) < 3:
                    continue

                avg_error = np.mean(errors)
                model_scores[model] += w * avg_error
                model_counts[model] += 1

        # require at least one mode
        return {
            m: model_scores[m]
            for m in model_scores
            if model_counts[m] > 0
        }

    # =========================
    # BEST MODEL
    # =========================
    def best_model_city(self, city):
        scores = self.compute_weighted_scores(city)

        if len(scores) < 2:
            return None, None

        sorted_models = sorted(scores.items(), key=lambda x: x[1])

        best = sorted_models[0]
        second = sorted_models[1]

        gap = second[1] - best[1]

        return best[0], gap

    # =========================
    # ALERTING
    # =========================
    def send_alert(self, city, level, msg):
        now = time.time()
        key = (city, level)

        if now - self.last_alert_time.get(key, 0) < self.alert_cooldowns[level]:
            self.alert_log.write([_now_iso(), city, level, msg, False])
            return

        self.last_alert_time[key] = now
        self.telegram.send(msg)
        self.alert_log.write([_now_iso(), city, level, msg, True])

    def detect_alerts(self, city):
        best, gap = self.best_model_city(city)
        prev = self.last_best_by_city.get(city)

        if prev and best and prev != best:
            self.metrics["flips"] += 1
            self.send_alert(city, "HIGH", f"🔁 Flip {city}: {prev} → {best}")

        if gap is not None and gap < 0.3:
            self.metrics["low_conf"] += 1
            self.send_alert(city, "LOW", f"⚠️ Low confidence {city}")

        if best:
            self.decision_log.write([
                _now_iso(),
                city,
                best,
                gap,
            ])

        self.last_best_by_city[city] = best

    # =========================
    # DAILY SUMMARY
    # =========================
    def daily_summary(self):
        lines = ["📊 DAILY SUMMARY"]

        for k, v in self.metrics.items():
            lines.append(f"{k}: {v}")

        return "\n".join(lines)

    def maybe_send_daily_summary(self):
        now = time.time()

        if now - self.last_daily_summary >= self.daily_summary_interval:
            self.last_daily_summary = now
            self.telegram.send(self.daily_summary())
