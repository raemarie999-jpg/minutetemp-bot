import os
import time
from collections import defaultdict, deque
from datetime import datetime, timezone

import numpy as np
from telegram_alerts import TelegramAlerts


def now():
    return datetime.now(timezone.utc)


class ModelEngine:
    def __init__(self):
        # -------------------------
        # DATA
        # -------------------------
        self.observations = {}
        self.forecasts = defaultdict(dict)

        # error tracking
        self.errors = defaultdict(lambda: defaultdict(lambda: deque(maxlen=100)))

        # oracle scores by mode
        self.oracle = defaultdict(lambda: defaultdict(dict))
        # city -> model -> {overall, day_ahead, day_of}

        # tracking
        self.last_best = {}
        self.last_predictive = {}
        self.last_alert_time = {}

        self.telegram = TelegramAlerts()

        self.cooldown = 300

        print("🧠 ModelEngine V2 initialized", flush=True)

    # -------------------------
    # ENTRY
    # -------------------------
    def process_event(self, event):
        t = event.get("type")

        if t == "observation":
            self.handle_observation(event)

        elif t == "forecast":
            self.handle_forecast(event)

        elif t == "oracle_scores":
            self.handle_oracle(event)

    # -------------------------
    # OBSERVATION
    # -------------------------
    def handle_observation(self, event):
        city = event.get("city")
        val = event.get("value")

        try:
            val = float(val)
        except:
            return

        self.observations[city] = val
        self.validate(city, val)

    # -------------------------
    # FORECAST
    # -------------------------
    def handle_forecast(self, event):
        city = event.get("city")
        models = event.get("models", [])

        count = 0

        for m in models:
            mid = m.get("model_id")
            val = m.get("value")

            if mid is None or val is None:
                continue

            try:
                val = float(val)
            except:
                continue

            self.forecasts[city][mid] = val
            count += 1

        if count:
            print(f"📊 {city}: {count} forecasts", flush=True)

    # -------------------------
    # ORACLE
    # -------------------------
    def handle_oracle(self, event):
        city = event.get("city")
        mode = event.get("mode", "overall")
        scores = event.get("scores", [])

        for s in scores:
            mid = s.get("model_id")
            mae = s.get("combined_mae")

            if mid is None or mae is None:
                continue

            try:
                mae = float(mae)
            except:
                continue

            self.oracle[city][mid][mode] = mae

        print(f"📈 {city}: oracle {mode} updated", flush=True)

    # -------------------------
    # VALIDATION
    # -------------------------
    def validate(self, city, actual):
        if city not in self.forecasts:
            return

        for mid, forecast in self.forecasts[city].items():
            err = abs(forecast - actual)
            self.errors[city][mid].append(err)

        self.rank(city)

    # -------------------------
    # CORE SCORING
    # -------------------------
    def compute_score(self, city, mid):
        errs = self.errors[city][mid]

        if len(errs) < 5:
            return None

        arr = np.array(errs)

        # 1. time-weighted error
        weights = np.linspace(0.5, 1.5, len(arr))
        weighted_error = np.average(arr, weights=weights)

        # 2. volatility penalty
        volatility = np.std(arr)

        # 3. trend (slope)
        slope = np.polyfit(range(len(arr)), arr, 1)[0]

        # 4. oracle blending
        oracle_block = self.oracle[city].get(mid, {})
        oracle_score = None

        if oracle_block:
            parts = []

            if "day_of" in oracle_block:
                parts.append(oracle_block["day_of"] * 1.2)

            if "day_ahead" in oracle_block:
                parts.append(oracle_block["day_ahead"] * 1.0)

            if "overall" in oracle_block:
                parts.append(oracle_block["overall"] * 0.6)

            if parts:
                oracle_score = np.mean(parts)

        # FINAL SCORE
        score = weighted_error
        score += 0.6 * volatility
        score += 0.8 * slope

        if oracle_score is not None:
            score = 0.6 * score + 0.4 * oracle_score

        return score

    # -------------------------
    # RANKING
    # -------------------------
    def rank(self, city):
        scores = {}

        for mid in self.forecasts[city]:
            s = self.compute_score(city, mid)
            if s is not None:
                scores[mid] = s

        if len(scores) < 2:
            return

        # LIVE BEST
        live_best = min(scores, key=scores.get)

        # PREDICTIVE BEST (trend-adjusted)
        predictive_scores = {}

        for mid in scores:
            errs = self.errors[city][mid]
            arr = np.array(errs)

            slope = np.polyfit(range(len(arr)), arr, 1)[0]
            predictive_scores[mid] = scores[mid] + slope

        pred_best = min(predictive_scores, key=predictive_scores.get)

        # CONFIDENCE
        sorted_vals = sorted(scores.values())
        gap = sorted_vals[1] - sorted_vals[0]

        if gap > 1.0:
            confidence = "HIGH"
        elif gap > 0.4:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"

        print(
            f"🏆 {city.upper()} LIVE: {live_best} | "
            f"PRED: {pred_best} | CONF: {confidence}",
            flush=True,
        )

        self.maybe_alert(city, live_best, pred_best, confidence)

        self.last_best[city] = live_best
        self.last_predictive[city] = pred_best

    # -------------------------
    # ALERTS
    # -------------------------
    def maybe_alert(self, city, live, pred, confidence):
        now_ts = time.time()

        if now_ts - self.last_alert_time.get(city, 0) < self.cooldown:
            return

        prev_live = self.last_best.get(city)
        prev_pred = self.last_predictive.get(city)

        if prev_live == live and prev_pred == pred:
            return

        self.last_alert_time[city] = now_ts

        msg = (
            f"🚨 MODEL UPDATE ({city.upper()})\n"
            f"Live: {prev_live} → {live}\n"
            f"Predictive: {prev_pred} → {pred}\n"
            f"Confidence: {confidence}"
        )

        print(msg, flush=True)

        try:
            self.telegram.send(msg)
        except Exception as e:
            print("❌ Telegram error:", repr(e), flush=True)

    # -------------------------
    # DAILY SUMMARY
    # -------------------------
    def maybe_send_daily_summary(self):
        pass
