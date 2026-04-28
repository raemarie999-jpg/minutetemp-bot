import time
from collections import defaultdict


class ModelEngine:
    def __init__(self):
        self.cities = defaultdict(lambda: {
            "temps": [],
            "forecasts": {},
            "scores": {
                "overall": {},
                "day_ahead": {},
                "day_of": {}
            },
            "errors": defaultdict(list),
            "weather_events": []
        })

        # ✅ unified timing control (no more broken state)
        self.last_reports = {}

    # -------------------------
    # OBSERVATIONS
    # -------------------------
    def process_observation(self, msg):
        city = msg.get("slug")
        temp = msg.get("temperature_f")

        if not city or temp is None:
            return

        try:
            temp = float(temp)
        except:
            return

        data = self.cities[city]

        data["temps"].append(temp)
        data["temps"] = data["temps"][-50:]

        self.validate_forecasts(city, temp)

    # -------------------------
    # FORECASTS
    # -------------------------
    def process_forecast(self, msg):
        city = msg.get("slug")
        forecasts = msg.get("forecasts", [])

        if not city:
            return

        for f in forecasts:
            model = f.get("model")
            temp = f.get("temp_f")

            if model and temp is not None:
                try:
                    self.cities[city]["forecasts"][model] = float(temp)
                except:
                    pass

    # -------------------------
    # SCORES
    # -------------------------
    def process_scores(self, msg):
        city = msg.get("slug")
        if not city:
            return

        def parse(block):
            return {
                s.get("model"): s.get("score")
                for s in block
                if s.get("model") and s.get("score") is not None
            }

        data = self.cities[city]

        data["scores"]["overall"] = parse(msg.get("overall", {}).get("scores", []))
        data["scores"]["day_ahead"] = parse(msg.get("day_ahead", {}).get("scores", []))
        data["scores"]["day_of"] = parse(msg.get("day_of", {}).get("scores", []))

    # -------------------------
    # WEATHER EVENTS
    # -------------------------
    def process_weather_event(self, msg):
        city = msg.get("slug")
        summary = msg.get("summary")

        if city and summary:
            data = self.cities[city]
            data["weather_events"].append(summary)
            data["weather_events"] = data["weather_events"][-20:]

    # -------------------------
    # VALIDATION
    # -------------------------
    def validate_forecasts(self, city, actual):
        forecasts = self.cities[city]["forecasts"]

        for model, pred in forecasts.items():
            error = abs(pred - actual)
            errs = self.cities[city]["errors"][model]
            errs.append(error)
            self.cities[city]["errors"][model] = errs[-20:]

    # -------------------------
    # SCORING
    # -------------------------
    def compute_score(self, city, model):
        data = self.cities[city]

        scores = data["scores"]
        errors = data["errors"]

        overall = scores["overall"].get(model, 0)
        day_ahead = scores["day_ahead"].get(model, 0)
        day_of = scores["day_of"].get(model, 0)

        base = (day_of * 0.5) + (day_ahead * 0.3) + (overall * 0.2)

        err_list = errors.get(model, [])
        penalty = (sum(err_list) / len(err_list)) * 0.05 if err_list else 0

        return base - penalty

    # -------------------------
    # REGIME
    # -------------------------
    def detect_regime(self, city):
        temps = self.cities[city]["temps"]
        events = self.cities[city]["weather_events"]

        if len(temps) < 5:
            return "INSUFFICIENT"

        if len(events) > 5:
            return "STORM"

        delta = temps[-1] - temps[0]

        if abs(delta) < 1:
            return "STABLE"
        elif abs(delta) < 3:
            return "TRANSITION"
        else:
            return "VOLATILE"

    # -------------------------
    # SIGNAL
    # -------------------------
    def generate_signal(self, ranked):
        if not ranked:
            return "NO DATA", "LOW"

        best, score = ranked[0]

        if score > 0.7:
            return f"STRONG BUY {best}", "HIGH"
        elif score > 0.4:
            return f"WEAK BUY {best}", "MEDIUM"
        else:
            return "NO TRADE", "LOW"

    # -------------------------
    # REPORT
    # -------------------------
    def generate_report(self, city):
        data = self.cities[city]

        temps = data["temps"]
        latest = round(temps[-1], 1) if temps else "N/A"

        all_models = set()
        for block in data["scores"].values():
            all_models.update(block.keys())

        ranked = []
        for m in all_models:
            ranked.append((m, self.compute_score(city, m)))

        ranked.sort(key=lambda x: x[1], reverse=True)

        regime = self.detect_regime(city)
        signal, confidence = self.generate_signal(ranked)

        lines = []
        lines.append("============================================================")
        lines.append(f"🏙 CITY INTELLIGENCE: {city.upper()}")
        lines.append("------------------------------------------------------------")
        lines.append(f"🌡 Temps: {len(temps)} latest={latest}")
        lines.append(f"🌪 Regime: {regime}")
        lines.append(f"📊 Signal: {signal} ({confidence})")
        lines.append("🏆 TOP MODELS:")

        if ranked:
            for i, (m, s) in enumerate(ranked[:5], 1):
                lines.append(f"{i}. {m} → {round(s, 3)}")
        else:
            lines.append("No model data yet")

        lines.append("============================================================")

        return "\n".join(lines)

    # -------------------------
    # REPORT LOOP
    # -------------------------
    def maybe_report(self):
        now = time.time()

        for city, data in self.cities.items():

            if city not in self.last_reports:
                self.last_reports[city] = 0

            temps = data["temps"]
            scores = data["scores"]

            has_scores = any(len(v) > 0 for v in scores.values())
            has_temps = len(temps) >= 3

            # warming phase
            if not has_scores or not has_temps:
                if now - self.last_reports[city] > 60:
                    print(f"⚠️ {city.upper()}: warming up (waiting for scores)", flush=True)
                    self.last_reports[city] = now
                continue

            # report phase
            if now - self.last_reports[city] > 60:
                report = self.generate_report(city)

                print(report, flush=True)

                # optional telegram
                if hasattr(self, "send_telegram"):
                    try:
                        self.send_telegram(report)
                    except:
                        pass

                self.last_reports[city] = now
