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


class CsvLogger:
    """Append-only CSV writer. Self-heals the header if the file is missing
    or empty (e.g. after manual log rotation)."""

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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ModelEngine:
    def __init__(self):
        self.rolling_errors = defaultdict(
            lambda: defaultdict(lambda: deque(maxlen=30))
        )

        self.forecasts = {}
        self.forecast_ttl = 60 * 30

        self.last_best_by_city = {}
        self.last_alert_time = {}

        self.telegram = TelegramAlerts()

        self.alert_cooldowns = {
            "HIGH": 120,
            "MEDIUM": 90,
            "LOW": 300,
        }

        self.last_daily_summary = 0
        self.daily_summary_interval = 60 * 60 * 24

        self.metrics = {
            "forecasts": 0,
            "observations": 0,
            "errors": 0,
            "flips": 0,
            "spikes": 0,
            "low_conf": 0,
        }

        self.obs_log = CsvLogger(
            os.path.join(LOG_DIR, "observations.csv"),
            ["ts", "city", "station_id", "value"],
        )
        self.scores_log = CsvLogger(
            os.path.join(LOG_DIR, "scores.csv"),
            [
                "ts", "city", "station_id", "mode", "model_id", "model_name",
                "combined_mae", "high_mae", "low_mae",
                "high_bias", "low_bias", "day_count",
            ],
        )
        self.decision_log = CsvLogger(
            os.path.join(LOG_DIR, "decisions.csv"),
            ["ts", "city", "live_best", "predictive_best", "gap"],
        )
        self.alert_log = CsvLogger(
            os.path.join(LOG_DIR, "alerts.csv"),
            ["ts", "city", "level", "message", "sent"],
        )

    # -------------------------
    # EVENT INGESTION
    # -------------------------
    def process_event(self, event):
        etype = event.get("type")

        if etype == "observation":
            self.metrics["observations"] += 1
            city = event.get("city")
            value = event.get("value")
            station = event.get("station_id")
            if city is not None and value is not None:
                self.obs_log.write([_now_iso(), city, station, value])

        elif etype == "oracle_scores":
            self.process_oracle_scores(event)

    # -------------------------
    # ORACLE SCORE INGESTION
    # MinuteTemp pre-computes 7-day rolling MAE per model and broadcasts it
    # via `oracle_scores_updated`. We treat each broadcast as a fresh data
    # point in our rolling history, then derive live + predictive winners.
    # -------------------------
    def process_oracle_scores(self, event):
        city = event.get("city")
        if not city:
            return

        station = event.get("station_id")
        mode = event.get("mode", "overall")
        scores = event.get("scores") or []

        ts = _now_iso()
        any_score = False

        for s in scores:
            model_id = s.get("model_id")
            mae = s.get("combined_mae")
            if model_id is None or mae is None:
                continue

            try:
                mae = float(mae)
            except (TypeError, ValueError):
                continue

            self.rolling_errors[city][model_id].append(mae)
            self.metrics["errors"] += 1
            any_score = True

            self.scores_log.write([
                ts, city, station, mode, model_id, s.get("model_name"),
                mae, s.get("high_mae"), s.get("low_mae"),
                s.get("high_bias"), s.get("low_bias"), s.get("day_count"),
            ])

        if any_score:
            self.detect_alerts(city)

    # -------------------------
    # BEST MODEL
    # -------------------------
    def best_model_city(self, city):
        scores = {
            m: np.mean(v)
            for m, v in self.rolling_errors[city].items()
            if len(v) >= 5
        }

        if len(scores) < 2:
            return None, None

        sorted_models = sorted(scores.items(), key=lambda x: x[1])
        return sorted_models[0][0], (sorted_models[1][1] - sorted_models[0][1])

    # -------------------------
    # PREDICTIVE MODEL
    # -------------------------
    def predictive_best_model(self, city):
        scores = {}

        for model, errors in self.rolling_errors[city].items():
            if len(errors) < 10:
                continue

            arr = np.array(errors)
            weighted = np.average(arr, weights=np.linspace(0.5, 1.5, len(arr)))
            slope = np.polyfit(np.arange(len(arr)), arr, 1)[0]
            vol = np.std(arr)

            scores[model] = weighted + 0.8 * slope + 0.5 * vol

        return min(scores, key=scores.get) if scores else None

    # -------------------------
    # ALERT SYSTEM
    # -------------------------
    def send_alert(self, city, level, msg):
        now = time.time()
        key = (city, level)

        if now - self.last_alert_time.get(key, 0) < self.alert_cooldowns[level]:
            self.alert_log.write([_now_iso(), city, level, msg, False])
            return

        self.last_alert_time[key] = now
        self.telegram.send(msg)
        self.alert_log.write([_now_iso(), city, level, msg, True])

    # -------------------------
    # ALERT LOGIC
    # -------------------------
    def detect_alerts(self, city):
        live_best, gap = self.best_model_city(city)
        pred_best = self.predictive_best_model(city)

        prev = self.last_best_by_city.get(city)

        if prev and live_best and prev != live_best:
            self.metrics["flips"] += 1
            self.send_alert(city, "HIGH", f"🔁 Flip {city}: {prev} → {live_best}")

        if gap is not None and gap < 0.5:
            self.metrics["low_conf"] += 1
            self.send_alert(city, "LOW", f"⚠️ Low confidence {city}")

        if pred_best and live_best and pred_best != live_best:
            self.send_alert(city, "HIGH", f"🔮 Shift {city}: {pred_best} → {live_best}")

        if live_best or pred_best:
            self.decision_log.write([_now_iso(), city, live_best, pred_best, gap])

        self.last_best_by_city[city] = live_best

    # -------------------------
    # DAILY SUMMARY
    # -------------------------
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
