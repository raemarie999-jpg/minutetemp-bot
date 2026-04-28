import time
from collections import defaultdict


class ModelEngine:
    def __init__(self):
        self.cities = defaultdict(lambda: {
            "temps": [],
            "forecasts": {},  # model -> temp prediction
            "scores": {
                "overall": {},
                "day_ahead": {},
                "day_of": {}
            },
            "errors": defaultdict(list),
            "weather_events": [],
            "last_report": 0,
            "initialized": time.time()
        })

    # -------------------------
    # OBSERVATIONS (LIVE DATA)
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

        c = self.cities[city]
        c["temps"].append(temp)
        c["temps"] = c["temps"][-50:]  # keep rolling window

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

            if model is None or temp is None:
                continue

            try:
                self.cities[city]["forecasts"][model] = float(temp)
            except:
                continue

    # -------------------------
    # ORACLE SCORES
    # -------------------------
    def process_scores(self, msg):
        city = msg.get("slug")
        if not city:
            return

        def parse(block):
            if not block:
                return {}
            return {
                s.get("model"): s.get("score")
                for s in block
                if s.get("model") and s.get("score") is not None
            }

        self.cities[city]["scores"]["overall"] = parse(msg.get("overall", {}).get("scores", []))
        self.cities[city]["scores"]["day_ahead"] = parse(msg.get("day_ahead", {}).get("scores", []))
        self.cities[city]["scores"]["day_of"] = parse(msg.get("day_of", {}).get("scores", []))

    # -------------------------
    # WEATHER EVENTS
    # -------------------------
    def process_weather_event(self, msg):
        city = msg.get("slug")
        summary = msg.get("summary")

        if not city or not summary:
            return

        c = self.cities[city]
        c["weather_events"].append(summary)
        c["weather_events"] = c["weather_events"][-30:]

    # -------------------------
    # FORECAST VALIDATION
    # -------------------------
    def validate_forecasts(self, city, actual_temp):
        forecasts = self.cities[city]["forecasts"]

        for model, predicted in forecasts.items():
            try:
                error = abs(float(predicted) - actual_temp)
                self.cities[city]["errors"][model].append(error)
                self.cities[city]["errors"][model] = self.cities[city]["errors"][model][-50:]
            except:
                continue

    # -------------------------
    # SCORING ENGINE
    # -------------------------
    def compute_score(self, city, model):
        c = self.cities[city]

        scores = c["scores"]
        errors = c["errors"].get(model, [])

        overall = scores["overall"].get(model, 0) or 0
        day_ahead = scores["day_ahead"].get(model, 0) or 0
        day_of = scores["day_of"].get(model, 0) or 0

        base = (day_of * 0.5) + (day_ahead * 0.3) + (overall * 0.2)

        if errors:
            avg_error = sum(errors) / len(errors)
            penalty = avg_error * 0.03
        else:
            penalty = 0

        return base - penalty

    # -------------------------
    # REGIME DETECTION
    # -------------------------
    def detect_regime(self, city):
        temps = self.cities[city]["temps"]
        events = self.cities[city]["weather_events"]

        if len(temps) < 5:
            return "INSUFFICIENT_DATA"

        if len(events) > 8:
            return "STORMY"

        delta = temps[-1] - temps[0]

        if abs(delta) < 1:
            return "STABLE"
        elif abs(delta) < 3:
            return "TRANSITIONAL"
        else:
            return "VOLATILE"

    # -------------------------
    # TRADE / DECISION SIGNAL
    # -------------------------
    def generate_signal(self, ranked):
        if not ranked:
            return "NO_SIGNAL", "LOW"

        best_model, best_score = ranked[0]

        spread = ranked[0][1] - ranked[-1][1] if len(ranked) > 1 else 0

        if len(ranked) >= 5 and spread > 0.5:
            return f"STRONG EDGE: {best_model}", "HIGH"
        elif len(ranked) >= 3:
            return f"WEAK EDGE: {best_model}", "MEDIUM"
        else:
            return "NO EDGE", "LOW"

    # -------------------------
    # REPORT GENERATION
    # -------------------------
    def generate_report(self, city):
        c = self.cities[city]

        all_models = set()
        for group in c["scores"].values():
            all_models.update(group.keys())

        if not all_models:
            return f"⚠️ {city.upper()}: waiting for model scores..."

        ranked = [(m, self.compute_score(city, m)) for m in all_models]
        ranked.sort(key=lambda x: x[1], reverse=True)

        regime = self.detect_regime(city)
        signal, confidence = self.generate_signal(ranked)

        lines = []
        lines.append("=" * 60)
        lines.append(f"🏙 CITY INTELLIGENCE REPORT: {city.upper()}")
        lines.append("=" * 60)
        lines.append(f"🌪 Regime: {regime}")
        lines.append(f"📊 Confidence: {confidence}")
        lines.append("")
        lines.append("🏆 TOP MODELS")

        for i, (m, s) in enumerate(ranked[:5], 1):
            lines.append(f"{i}. {m:<15} → {s:.3f}")

        lines.append("")
        lines.append(f"🎯 SIGNAL: {signal}")
        lines.append("=" * 60)

        return "\n".join(lines)

    # -------------------------
    # REPORT LOOP (FIXED + RELIABLE)
    # -------------------------
    def maybe_report(self):
        now = time.time()

        for city, data in self.cities.items():

            temps = data["temps"]
            scores = data["scores"]

            has_temps = len(temps) >= 3
            has_scores = any(len(v) > 0 for v in scores.values())

            # warming phase
            if not has_temps or not has_scores:
                if now - data["last_report"] > 60:
                    print(f"⚠️ {city.upper()}: warming up (collecting data...)", flush=True)
                    data["last_report"] = now
                continue

            # report phase
            if now - data["last_report"] > 60:
                print(self.generate_report(city), flush=True)
                data["last_report"] = now
