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
# CSV LOGGER
# -------------------------
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
            print("⚠️ CSV error:", repr(e), flush=True)


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# -------------------------
# MODEL ENGINE v2
# -------------------------
class ModelEngine:
    """
    Two-mode system:

    1) OVERALL MODE (slow signal)
       - uses: overall oracle_scores
       - stable ranking

    2) SHORT TERM MODE (fast signal)
       - uses: day_ahead + day_of
       - reactive / live reliability
    """

    def __init__(self):
        # city -> mode -> model -> deque(errors)
        self.errors = defaultdict(
            lambda: {
                "overall": defaultdict(lambda: deque(maxlen=30)),
                "short": defaultdict(lambda: deque(maxlen=30)),
            }
        )

        self.last_best = {}  # city -> model
        self.last_alert_time = {}

        self.telegram = TelegramAlerts()

        self.alert_cooldowns = {
            "HIGH": 120,
            "MEDIUM": 90,
            "LOW": 300,
        }

        self.metrics = {
            "observations": 0,
            "oracle_updates": 0,
            "flips": 0,
            "alerts": 0,
        }

        # logs
        self.obs_log = CsvLogger(
            os.path.join(LOG_DIR, "observations.csv"),
            ["ts", "city", "station_id", "value"],
        )

        self.oracle_log = CsvLogger(
            os.path.join(LOG_DIR, "oracle.csv"),
            ["ts", "city", "mode", "model_id", "mae"],
        )

        self.alert_log = CsvLogger(
            os.path.join(LOG_DIR, "alerts.csv"),
            ["ts", "city", "level", "msg", "sent"],
        )

    # -------------------------
    # EVENT ENTRY
    # -------------------------
    def process_event(self, event):
        if event["type"] == "observation":
            self.metrics["observations"] += 1
            self._obs(event)

        elif event["type"] == "oracle_scores":
            self.metrics["oracle_updates"] += 1
            self._oracle(event)

    # -------------------------
    # OBSERVATIONS
    # -------------------------
    def _obs(self, e):
        self.obs_log.write([
            _now(),
            e["city"],
            e.get("station_id"),
            e["value"],
        ])

    # -------------------------
    # ORACLE SCORES (CORE FIX HERE)
    # -------------------------
    def _oracle(self, e):
        city = e["city"]
        mode = e.get("mode", "overall")
        scores = e.get("scores", [])

        bucket = "overall" if mode == "overall" else "short"

        for s in scores:
            mid = s.get("model_id")
            mae = s.get("combined_mae")
            if mid is None or mae is None:
                continue

            try:
                mae = float(mae)
            except:
                continue

            self.errors[city][bucket][mid].append(mae)

            self.oracle_log.write([
                _now(),
                city,
                bucket,
                mid,
                mae,
            ])

        self._evaluate(city)

    # -------------------------
    # CORE RANKING
    # -------------------------
    def _rank(self, city, bucket):
        scores = {}

        for model, vals in self.errors[city][bucket].items():
            if len(vals) < 5:
                continue
            scores[model] = float(np.mean(vals))

        if len(scores) < 2:
            return None

        return sorted(scores.items(), key=lambda x: x[1])

    # -------------------------
    # BEST MODELS
    # -------------------------
    def _best_overall(self, city):
        r = self._rank(city, "overall")
        return r[0][0] if r else None

    def _best_short(self, city):
        r = self._rank(city, "short")
        return r[0][0] if r else None

    # -------------------------
    # ALERT LOGIC
    # -------------------------
    def _evaluate(self, city):
        overall_best = self._best_overall(city)
        short_best = self._best_short(city)

        if not overall_best or not short_best:
            return

        prev = self.last_best.get(city)

        # flip detection (short-term only)
        if prev and prev != short_best:
            self.metrics["flips"] += 1
            self._alert(city, "HIGH", f"🔁 Flip {city}: {prev} → {short_best}")

        # divergence signal (important insight)
        if overall_best != short_best:
            self._alert(
                city,
                "MEDIUM",
                f"⚠️ Divergence {city}: long={overall_best} short={short_best}",
            )

        self.last_best[city] = short_best

    # -------------------------
    # TELEGRAM ALERTS
    # -------------------------
    def _alert(self, city, level, msg):
        now = time.time()
        key = (city, level)

        if now - self.last_alert_time.get(key, 0) < self.alert_cooldowns[level]:
            self.alert_log.write([_now(), city, level, msg, False])
            return

        self.last_alert_time[key] = now
        self.telegram.send(msg)
        self.metrics["alerts"] += 1

        self.alert_log.write([_now(), city, level, msg, True])

    # -------------------------
    # OPTIONAL SUMMARY
    # -------------------------
    def daily_summary(self):
        return (
            "📊 DAILY SUMMARY\n"
            + "\n".join(f"{k}: {v}" for k, v in self.metrics.items())
        )

    def maybe_send_daily_summary(self):
        # kept for compatibility (no-op timing logic can be added later)
        pass
