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

        # report throttle tracking
        self.last_report = defaultdict(lambda: 0)

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
        if not city:
            return

        for f in msg.get("forecasts", []):
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
    # FORECAST VALIDATION
    # -------------------------
    def validate_forecasts(self, city, actual):
        forecasts = self.cities[city]["forecasts"]

        for model, pred in forecasts.items():
            err = abs(pred - actual)
            self.cities[city]["errors"][model].append(err)
            self.cities[city]["errors"][model] = self.cities[city]["errors"][model][-20:]

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
    # REGIME DETECTION
    # -------------------------
    def detect_regime(self, city):
        temps = self.cities[city]["temps"]
        events = self.cities[city]["weather_events"]

        if len(temps) < 3:
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
    # SIGNAL GENERATION
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
    # REPORT ENGINE (FIXED)
    # -------------------------
    def generate_report(self, city):
        data = self.cities[city]

        temps = data["temps"]
        latest = round(temps[-1], 1) if temps else "N/A"

        models = set()
        for block in data["scores"].values():
            models.update(block.keys())

        ranked = [(m, self.compute_score(city, m)) for m in models]
        ranked.sort(key=lambda x: x[1], reverse=True)

        regime = self.detect_regime(city)
        signal, confidence = self.generate_signal(ranked)

        lines = []
        lines.append("=" * 60)
        lines.append(f"🏙 CITY INTELLIGENCE: {city.upper()}")
        lines.append("-" * 60)
        lines.append(f"🌡 Temps: {len(temps)} latest={latest}")
        lines.append(f"🌪 Regime: {regime}")
        lines.append(f"📊 Signal: {signal} ({confidence})")
        lines.append("")
        lines.append("🏆 TOP MODELS:")

        if ranked:
            for i, (m, s) in enumerate(ranked[:5], 1):
                lines.append(f"{i}. {m} → {round(s, 3)}")
        else:
            lines.append("No model data yet")

        lines.append("=" * 60)

        return "\n".join(lines)

    # -------------------------
    # REPORT LOOP (THIS IS THE KEY FIX)
    # -------------------------
    def maybe_report(self):
        now = time.time()

        for city, data in self.cities.items():

            temps = data["temps"]

            # 🚨 ONLY REQUIRE TEMPS (NOT SCORES)
            if len(temps) < 3:
                if now - self.last_report[city] > 60:
                    print(f"⚠️ {city.upper()}: warming up (collecting data...)", flush=True)
                    self.last_report[city] = now
                continue

            # report every 60s
            if now - self.last_report[city] > 60:
                print(self.generate_report(city), flush=True)
                self.last_report[city] = now
