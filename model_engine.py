import time
from collections import defaultdict


class ModelEngine:
    def __init__(self):
        self.cities = defaultdict(lambda: {
            "temps": [],
            "forecasts": {},  # model -> temp
            "scores": {
                "overall": {},
                "day_ahead": {},
                "day_of": {}
            },
            "errors": defaultdict(list),
            "weather_events": [],
            "last_report": 0,
            "last_activity": time.time()
        })

        self.report_interval = 60  # seconds

    # -------------------------
    # OBSERVATIONS
    # -------------------------
    def process_observation(self, msg):
        city = msg.get("slug")
        temp = msg.get("temperature_f")

        if not city:
            return

        try:
            temp = float(temp)
        except:
            return

        self.cities[city]["temps"].append(temp)
        self.cities[city]["temps"] = self.cities[city]["temps"][-50:]
        self.cities[city]["last_activity"] = time.time()

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

            if not model:
                continue

            try:
                self.cities[city]["forecasts"][model] = float(temp)
            except:
                continue

    # -------------------------
    # SCORES
    # -------------------------
    def process_scores(self, msg):
        city = msg.get("slug")
        if not city:
            return

        def parse(block):
            if not isinstance(block, list):
                return {}
            return {
                s.get("model"): s.get("score")
                for s in block
                if s.get("model") and s.get("score") is not None
            }

        self.cities[city]["scores"]["overall"] = parse(msg.get("overall", {}).get("scores", []))
        self.cities[city]["scores"]["day_ahead"] = parse(msg.get("day_ahead", {}).get("scores", []))
        self.cities[city]["scores"]["day_of"] = parse(msg.get("day_of", {}).get("scores", []))

        self.cities[city]["last_activity"] = time.time()

    # -------------------------
    # WEATHER EVENTS
    # -------------------------
    def process_weather_event(self, msg):
        city = msg.get("slug")
        summary = msg.get("summary")

        if not city or not summary:
            return

        self.cities[city]["weather_events"].append(summary)
        self.cities[city]["weather_events"] = self.cities[city]["weather_events"][-30:]

    # -------------------------
    # VALIDATION
    # -------------------------
    def validate_forecasts(self, city, actual_temp):
        forecasts = self.cities[city]["forecasts"]

        for model, predicted in forecasts.items():
            try:
                error = abs(float(predicted) - actual_temp)
            except:
                continue

            self.cities[city]["errors"][model].append(error)
            self.cities[city]["errors"][model] = self.cities[city]["errors"][model][-30:]

    # -------------------------
    # SCORING
    # -------------------------
    def compute_score(self, city, model):
        scores = self.cities[city]["scores"]
        errors = self.cities[city]["errors"]

        overall = scores["overall"].get(model, 0) or 0
        day_ahead = scores["day_ahead"].get(model, 0) or 0
        day_of = scores["day_of"].get(model, 0) or 0

        base = (day_of * 0.5) + (day_ahead * 0.3) + (overall * 0.2)

        err_list = errors.get(model, [])
        if err_list:
            avg_error = sum(err_list) / len(err_list)
            base -= avg_error * 0.05

        return base

    # -------------------------
    # REGIME DETECTION
    # -------------------------
    def detect_regime(self, city):
        temps = self.cities[city]["temps"]
        events = self.cities[city]["weather_events"]

        if len(temps) < 3:
            return "INSUFFICIENT DATA"

        if len(events) > 8:
            return "STORMY"

        change = abs(temps[-1] - temps[0])

        if change < 1:
            return "STABLE"
        elif change < 4:
            return "TRANSITIONAL"
        else:
            return "VOLATILE"

    # -------------------------
    # SIGNAL
    # -------------------------
    def generate_signal(self, ranked):
        if not ranked:
            return "NO DATA", "LOW"

        best_model, best_score = ranked[0]

        if len(ranked) < 3:
            return f"WEAK SIGNAL → {best_model}", "LOW"

        if best_score > 0.7:
            return f"STRONG SIGNAL → {best_model}", "HIGH"

        return f"MODERATE SIGNAL → {best_model}", "MEDIUM"

    # -------------------------
    # REPORT
    # -------------------------
    def generate_report(self, city):
        data = self.cities[city]

        models = set()
        for block in data["scores"].values():
            models.update(block.keys())

        if not models:
            return f"⚠️ {city.upper()}: collecting model data..."

        ranked = [(m, self.compute_score(city, m)) for m in models]
        ranked.sort(key=lambda x: x[1], reverse=True)

        regime = self.detect_regime(city)
        signal, confidence = self.generate_signal(ranked)

        lines = []
        lines.append("=" * 60)
        lines.append(f"🏙 CITY REPORT: {city.upper()}")
        lines.append("=" * 60)
        lines.append(f"🌡 Temps: {len(data['temps'])}")
        lines.append(f"🌪 Regime: {regime}")
        lines.append(f"📊 Confidence: {confidence}")
        lines.append("")
        lines.append("🏆 TOP MODELS:")

        for i, (m, s) in enumerate(ranked[:5], 1):
            lines.append(f"{i}. {m:<12} → {s:.3f}")

        lines.append("")
        lines.append(f"🎯 SIGNAL: {signal}")
        lines.append("=" * 60)

        return "\n".join(lines)

    # -------------------------
    # REPORT LOOP (FIXED)
    # -------------------------
    def maybe_report(self):
        now = time.time()

        for city, data in self.cities.items():

            # always show activity state
            has_any_data = len(data["temps"]) > 0 or len(data["scores"]["overall"]) > 0

            if not has_any_data:
                continue

            # cooldown logic
            if now - data["last_report"] < self.report_interval:
                continue

            print(self.generate_report(city), flush=True)
            data["last_report"] = now
