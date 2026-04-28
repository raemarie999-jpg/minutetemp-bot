import time
from collections import defaultdict


class ModelEngine:
    def __init__(self):
        self.cities = defaultdict(lambda: {
            "temps": [],
            "forecasts": {},          # model -> predicted temp
            "scores": {
                "overall": {},
                "day_ahead": {},
                "day_of": {}
            },
            "errors": defaultdict(list),
            "weather_events": [],
            "last_report": 0,
            "last_signal": None
        })

    # -------------------------
    # OBSERVATIONS
    # -------------------------
    def process_observation(self, msg):
        city = msg.get("slug")
        temp = msg.get("temperature_f")

        if city is None or temp is None:
            return

        try:
            temp = float(temp)
        except:
            return

        self.cities[city]["temps"].append(temp)
        self.cities[city]["temps"] = self.cities[city]["temps"][-50:]

        # validate forecasts against truth
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

            if not model or temp is None:
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
            out = {}
            for s in block:
                m = s.get("model")
                sc = s.get("score")
                if m and sc is not None:
                    out[m] = float(sc)
            return out

        self.cities[city]["scores"]["overall"] = parse(msg.get("overall", {}).get("scores", []))
        self.cities[city]["scores"]["day_ahead"] = parse(msg.get("day_ahead", {}).get("scores", []))
        self.cities[city]["scores"]["day_of"] = parse(msg.get("day_of", {}).get("scores", []))

    # -------------------------
    # WEATHER EVENTS
    # -------------------------
    def process_weather_event(self, msg):
        city = msg.get("slug")
        summary = msg.get("summary", "")

        if city:
            self.cities[city]["weather_events"].append(summary)
            self.cities[city]["weather_events"] = self.cities[city]["weather_events"][-30:]

    # -------------------------
    # VALIDATION (forecast error tracking)
    # -------------------------
    def validate_forecasts(self, city, actual):
        forecasts = self.cities[city]["forecasts"]

        for model, pred in forecasts.items():
            err = abs(pred - actual)
            self.cities[city]["errors"][model].append(err)
            self.cities[city]["errors"][model] = self.cities[city]["errors"][model][-30:]

    # -------------------------
    # SCORING MODEL
    # -------------------------
    def compute_score(self, city, model):
        scores = self.cities[city]["scores"]
        errors = self.cities[city]["errors"]

        base = (
            scores["overall"].get(model, 0) * 0.5 +
            scores["day_ahead"].get(model, 0) * 0.3 +
            scores["day_of"].get(model, 0) * 0.2
        )

        err = errors.get(model, [])
        penalty = (sum(err) / len(err)) * 0.05 if err else 0

        return base - penalty

    # -------------------------
    # REGIME DETECTION
    # -------------------------
    def detect_regime(self, city):
        temps = self.cities[city]["temps"]
        events = self.cities[city]["weather_events"]

        if len(temps) < 5:
            return "INSUFFICIENT DATA"

        if len(events) > 5:
            return "STORMY / ACTIVE"

        delta = temps[-1] - temps[0]

        if abs(delta) < 1:
            return "STABLE"
        elif abs(delta) < 3:
            return "TRANSITIONAL"
        else:
            return "VOLATILE"

    # -------------------------
    # SIGNAL GENERATION
    # -------------------------
    def generate_signal(self, ranked):
        if not ranked:
            return "NO DATA", 0

        best_model, best_score = ranked[0]

        if best_score > 0.7:
            return f"STRONG BUY: {best_model}", best_score
        elif best_score > 0.4:
            return f"WEAK BUY: {best_model}", best_score
        else:
            return "NO EDGE", best_score

    # -------------------------
    # REPORT
    # -------------------------
    def generate_report(self, city):
        data = self.cities[city]

        models = set()
        for block in data["scores"].values():
            models.update(block.keys())

        if not models:
            return f"⚠️ {city.upper()} | collecting data..."

        ranked = [(m, self.compute_score(city, m)) for m in models]
        ranked.sort(key=lambda x: x[1], reverse=True)

        regime = self.detect_regime(city)
        signal, strength = self.generate_signal(ranked)

        lines = []
        lines.append("=" * 60)
        lines.append(f"🏙 CITY REPORT: {city.upper()}")
        lines.append("=" * 60)
        lines.append(f"🌪 Regime: {regime}")
        lines.append("")
        lines.append("🏆 TOP MODELS:")

        for i, (m, s) in enumerate(ranked[:5], 1):
            lines.append(f"{i}. {m:<15} | score={s:.3f}")

        lines.append("")
        lines.append(f"🎯 SIGNAL: {signal} (strength={strength:.3f})")
        lines.append("=" * 60)

        return "\n".join(lines)

    # -------------------------
    # REPORT LOOP (THIS IS THE FIX)
    # -------------------------
    def maybe_report(self):
        now = time.time()

        for city, data in self.cities.items():
            temps = data["temps"]

            has_any_data = len(temps) > 0 or len(data["scores"]["overall"]) > 0

            if not has_any_data:
                continue

            # ALWAYS report every 60s once data exists
            if now - data["last_report"] > 60:
                print(self.generate_report(city), flush=True)
                data["last_report"] = now
