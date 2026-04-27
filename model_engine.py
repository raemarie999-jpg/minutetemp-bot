import os
import time
from collections import defaultdict, deque
from datetime import datetime, timezone

import numpy as np

from telegram_alerts import TelegramAlerts


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ModelEngine:
    def __init__(self):
        # city -> model -> deque of recent errors
        self.errors = defaultdict(lambda: defaultdict(lambda: deque(maxlen=50)))

        # last decision per city
        self.current_best = {}
        self.last_alert_time = {}

        self.telegram = TelegramAlerts()

        # cooldowns to avoid spam
        self.cooldowns = {
            "CHANGE": 120,
            "WEAK": 300,
        }

        # weights for different oracle modes
        self.mode_weights = {
            "day_of": 1.5,
            "day_ahead": 1.2,
            "overall": 1.0,
        }

    # -------------------------
    # MAIN ENTRY
    # -------------------------
    def process_event(self, event):
        etype = event.get("type")

        if etype == "oracle_scores":
            self._handle_scores(event)

        elif etype == "observation":
            # currently unused for ranking (future expansion)
            pass

        elif etype == "forecast":
            # placeholder for future forecast evaluation
            pass

    # -------------------------
    # INGEST SCORES
    # -------------------------
    def _handle_scores(self, event):
        city = event.get("city")
        scores = event.get("scores") or []
        mode = event.get("mode", "overall")

        if not city or not scores:
            return

        weight = self.mode_weights.get(mode, 1.0)

        for s in scores:
            model = s.get("model_id")
            mae = s.get("combined_mae")

            if model is None or mae is None:
                continue

            try:
                mae = float(mae)
            except:
                continue

            # weighted insert (more weight = more influence)
            self.errors[city][model].append(mae * weight)

        self._evaluate_city(city)

    # -------------------------
    # CORE LOGIC
    # -------------------------
    def _evaluate_city(self, city):
        model_scores = {}

        for model, vals in self.errors[city].items():
            if len(vals) < 5:
                continue

            arr = np.array(vals)

            avg = np.mean(arr)
            trend = np.polyfit(range(len(arr)), arr, 1)[0]  # slope
            vol = np.std(arr)

            # lower is better
            score = avg + 0.7 * trend + 0.5 * vol

            model_scores[model] = score

        if len(model_scores) < 2:
            return

        ranked = sorted(model_scores.items(), key=lambda x: x[1])

        best_model, best_score = ranked[0]
        second_score = ranked[1][1]

        gap = second_score - best_score

        prev_best = self.current_best.get(city)

        # -------------------------
        # PRINT ALWAYS (LIVE OUTPUT)
        # -------------------------
        print(
            f"🏆 BEST {city.upper()} → {best_model} "
            f"(gap: {gap:.3f})",
            flush=True,
        )

        # -------------------------
        # ALERTS
        # -------------------------
        if prev_best and prev_best != best_model:
            self._alert(city, "CHANGE",
                        f"🔁 {city.upper()} model flip: {prev_best} → {best_model}")

        if gap < 0.3:
            self._alert(city, "WEAK",
                        f"⚠️ {city.upper()} weak signal (models close)")

        self.current_best[city] = best_model

    # -------------------------
    # ALERT SYSTEM
    # -------------------------
    def _alert(self, city, level, msg):
        now_ts = time.time()
        key = (city, level)

        if now_ts - self.last_alert_time.get(key, 0) < self.cooldowns[level]:
            return

        self.last_alert_time[key] = now_ts

        print(f"🚨 ALERT: {msg}", flush=True)
        self.telegram.send(msg)

    # -------------------------
    # DAILY SUMMARY (OPTIONAL)
    # -------------------------
    def maybe_send_daily_summary(self):
        pass
