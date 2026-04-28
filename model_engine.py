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
            "weather_events": [],
            "last_report": 0
        })

    # -------------------------
    # DATA INGESTION
    # -------------------------
    def process_observation(self, msg):
        city = msg.get("slug")
        temp = msg.get("temperature_f")

        if city and temp is not None:
            try:
                temp = float(temp)
                self.cities[city]["temps"].append(temp)
                self.cities[city]["temps"] = self.cities[city]["temps"][-50:]
                self.validate_forecasts(city, temp)
            except:
                pass

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

        self.cities[city]["scores"]["overall"] = parse(msg.get("overall", {}).get("scores", []))
        self.cities[city]["scores"]["day_ahead"] = parse(msg.get("day_ahead", {}).get("scores", []))
        self.cities[city]["scores"]["day_of"] = parse(msg.get("day_of", {}).get("scores", []))

    def process_weather_event(self, msg):
        city = msg.get("slug")
        summary = msg.get("summary", "")

        if city:
            self.cities[city]["weather_events"].append(summary)
            self.cities[city]["weather_events"] = self.cities[city]["weather_events"][-20:]

    # -------------------------
    # CORE LOGIC
    # -------------------------
    def validate_forecasts(self, city, actual):
        forecasts = self.cities[city]["forecasts"]

        for model, pred in forecasts.items():
            error = abs(pred - actual)
            self.cities[city]["errors"][model].append(error)
            self.cities[city]["errors"][model] = self.cities[city]["errors"][model][-20:]

    def compute_score(self, city, model):
        scores = self.cities[city]["scores"]
        errors = self.cities[city]["errors"]

        base = (
            scores["day_of"].get(model, 0) * 0.5 +
            scores["day_ahead"].get(model, 0) * 0.3 +
            scores["overall"].get(model, 0) * 0.2
        )

        err_list = errors.get(model, [])
        penalty = (sum(err_list) / len(err_list)) * 0.05 if err_list else 0

        return base - penalty

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

    # 🔥 KEY FIX: USE FORECASTS IF NO SCORES
    def generate_signal(self, city):
        data = self.cities[city]
        forecasts = data["forecasts"]
        temps = data["temps"]

        if not forecasts:
            return "NO FORECAST DATA", "LOW"

        latest = temps[-1] if temps else None

        diffs = [(m, abs(f - latest)) for m, f in forecasts.items()] if latest else []

        if diffs:
            diffs.sort(key=lambda x: x[1])
            best = diffs[0][0]
            return f"MODEL EDGE → {best}", "MEDIUM"

        return "NO SIGNAL", "LOW"

    # -------------------------
    # REPORT
    # -------------------------
    def generate_report(self, city):
        data = self.cities[city]
        temps = data["temps"]

        regime = self.detect_regime(city)
        signal, confidence = self.generate_signal(city)

        lines = []
        lines.append("=" * 60)
        lines.append(f"🏙 CITY INTELLIGENCE: {city.upper()}")
        lines.append("-" * 60)

        if temps:
            lines.append(f"🌡 Temps: {len(temps)} latest={round(temps[-1],1)}")
        else:
            lines.append("🌡 Temps: NO DATA")

        lines.append(f"🌪 Regime: {regime}")
        lines.append(f"📊 Signal: {signal} ({confidence})")

        forecasts = data["forecasts"]
        if forecasts:
            lines.append("\n📈 FORECAST SNAPSHOT:")
            for m, t in list(forecasts.items())[:5]:
                lines.append(f"{m}: {round(t,1)}°F")
        else:
            lines.append("\nNo forecast data")

        lines.append("=" * 60)

        return "\n".join(lines)

    # -------------------------
    # REPORT LOOP
    # -------------------------
    def maybe_report(self):
        now = time.time()

        for city, data in self.cities.items():
            if now - data["last_report"] > 60:
                print(self.generate_report(city), flush=True)
                data["last_report"] = now
