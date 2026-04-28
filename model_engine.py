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
            "last_report": 0
        })

    # -------------------------
    # OBSERVATIONS
    # -------------------------
    def process_observation(self, msg):
        city = msg.get("slug")
        temp = msg.get("temperature_f")

        if city and temp is not None:
            try:
                temp = float(temp)

                self.cities[city]["temps"].append(temp)
                self.cities[city]["temps"] = self.cities[city]["temps"][-30:]

                self.validate_forecasts(city, temp)

            except:
                pass

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
    # ORACLE SCORES
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

        self.cities[city]["scores"]["overall"] = parse(
            msg.get("overall", {}).get("scores", [])
        )
        self.cities[city]["scores"]["day_ahead"] = parse(
            msg.get("day_ahead", {}).get("scores", [])
        )
        self.cities[city]["scores"]["day_of"] = parse(
            msg.get("day_of", {}).get("scores", [])
        )

    # -------------------------
    # WEATHER EVENTS
    # -------------------------
    def process_weather_event(self, msg):
        city = msg.get("slug")
        summary = msg.get("summary", "")

        if city:
            self.cities[city]["weather_events"].append(summary)
            self.cities[city]["weather_events"] = self.cities[city]["weather_events"][-20:]

    # -------------------------
    # VALIDATION
    # -------------------------
    def validate_forecasts(self, city, actual_temp):
        forecasts = self.cities[city]["forecasts"]

        for model, predicted in forecasts.items():
            try:
                error = abs(float(predicted) - float(actual_temp))
                self.cities[city]["errors"][model].append(error)
                self.cities[city]["errors"][model] = self.cities[city]["errors"][model][-20:]
            except:
                continue

    # -------------------------
    # SCORING
    # -------------------------
    def compute_score(self, city, model):
        scores = self.cities[city]["scores"]
        errors = self.cities[city]["errors"]

        overall = scores["overall"].get(model, 0)
        day_ahead = scores["day_ahead"].get(model, 0)
        day_of = scores["day_of"].get(model, 0)

        base = (day_of * 0.5) + (day_ahead * 0.3) + (overall * 0.2)

        err_list = errors.get(model, [])
        if err_list:
            avg_error = sum(err_list) / len(err_list)
            penalty = avg_error * 0.05
        else:
            penalty = 0

        return base - penalty

    # -------------------------
    # REGIME DETECTION
    # -------------------------
    def detect_regime(self, city):
        temps = self.cities[city]["temps"]
        events = self.cities[city]["weather_events"]

        if len(events) > 5:
            return "STORM"

        if len(temps) < 5:
            return "UNKNOWN"

        delta = temps[-1] - temps[0]

        if abs(delta) < 1:
            return "STABLE"
        elif abs(delta) < 3:
            return "TRENDING"
        else:
            return "VOLATILE"

    # -------------------------
    # TRADE SIGNAL
    # -------------------------
    def generate_signal(self, city, ranked):
        if not ranked:
            return "NO DATA", "LOW"

        best, best_score = ranked[0]

        confidence = "LOW"
        if len(ranked) >= 5:
            confidence = "MEDIUM"
        if len(ranked) >= 10:
            confidence = "HIGH"

        if confidence == "HIGH" and best_score > 0.7:
            return f"STRONG BUY {best}", confidence
        elif confidence == "MEDIUM":
            return f"WEAK BUY {best}", confidence
        else:
            return "NO TRADE", confidence

    # -------------------------
    # REPORT
    # -------------------------
    def generate_report(self, city):
        data = self.cities[city]

        all_models = set()
        for m in data["scores"].values():
            all_models.update(m.keys())

        if not all_models:
            return f"⚠️ {city}: gathering data..."

        ranked = [(m, self.compute_score(city, m)) for m in all_models]
        ranked.sort(key=lambda x: x[1], reverse=True)

        regime = self.detect_regime(city)
        signal, confidence = self.generate_signal(city, ranked)

        lines = []
        lines.append("============================================================")
        lines.append(f"🏙 CITY INTELLIGENCE: {city.upper()}")
        lines.append("------------------------------------------------------------")
        lines.append(f"🌪 Regime: {regime}")
        lines.append(f"📊 Confidence: {confidence}")
        lines.append("")
        lines.append("🏆 TOP MODELS:")

        for i, (m, s) in enumerate(ranked[:5], 1):
            lines.append(f"{i}. {m} → {round(s, 3)}")

        lines.append("")
        lines.append(f"🎯 SIGNAL: {signal}")
        lines.append("============================================================")

        return "\n".join(lines)

    # -------------------------
    # LOOP / REPORTING
    # -------------------------
    def maybe_report(self):
        now = time.time()

        for city, data in self.cities.items():
            temps = data["temps"]
            scores = data["scores"]

            has_scores = any(len(v) > 0 for v in scores.values())
            has_temps = len(temps) >= 3

            # warming up state
            if not has_scores or not has_temps:
                if now - data["last_report"] > 60:
                    print(f"⚠️ {city}: warming up (need temps + scores)", flush=True)
                    data["last_report"] = now
                continue

            # report state
            if now - data["last_report"] > 60:
                print(self.generate_report(city), flush=True)
                data["last_report"] = now
