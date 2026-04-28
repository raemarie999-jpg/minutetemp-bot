import time
from collections import defaultdict, deque


class ModelEngineV3:
    """
    Stable intelligence engine:
    - collects observations
    - tracks forecast errors
    - ranks models
    - emits reports every 60s per city
    """

    def __init__(self):
        self.cities = defaultdict(lambda: {
            "temps": deque(maxlen=50),
            "forecasts": {},
            "scores": {
                "overall": {},
                "day_ahead": {},
                "day_of": {}
            },
            "errors": defaultdict(lambda: deque(maxlen=50)),
            "weather_events": deque(maxlen=50),
            "last_report": 0
        })

    # -------------------------
    # OBSERVATION
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
                s.get("model"): float(s.get("score"))
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

        if city and summary:
            self.cities[city]["weather_events"].append(summary)

    # -------------------------
    # VALIDATION
    # -------------------------
    def validate_forecasts(self, city, actual):
        forecasts = self.cities[city]["forecasts"]

        for model, pred in forecasts.items():
            try:
                err = abs(float(pred) - float(actual))
                self.cities[city]["errors"][model].append(err)
            except:
                continue

    # -------------------------
    # SCORING
    # -------------------------
    def compute_score(self, city, model):
        s = self.cities[city]["scores"]
        e = self.cities[city]["errors"]

        base = (
            s["overall"].get(model, 0) * 0.2 +
            s["day_ahead"].get(model, 0) * 0.3 +
            s["day_of"].get(model, 0) * 0.5
        )

        err = e.get(model, [])
        penalty = (sum(err) / len(err)) * 0.05 if err else 0

        return base - penalty

    # -------------------------
    # REGIME
    # -------------------------
    def detect_regime(self, city):
        temps = list(self.cities[city]["temps"])
        events = self.cities[city]["weather_events"]

        if len(events) >= 5:
            return "STORM"

        if len(temps) < 3:
            return "COLD_START"

        delta = temps[-1] - temps[0]

        if abs(delta) < 1:
            return "STABLE"
        elif abs(delta) < 3:
            return "TRENDING"
        else:
            return "VOLATILE"

    # -------------------------
    # SIGNAL
    # -------------------------
    def generate_signal(self, ranked):
        if not ranked:
            return "NO SIGNAL", "LOW"

        best, score = ranked[0]

        if len(ranked) >= 5 and score > 0.7:
            return f"STRONG: {best}", "HIGH"
        elif len(ranked) >= 3:
            return f"WEAK: {best}", "MEDIUM"
        else:
            return "NO SIGNAL", "LOW"

    # -------------------------
    # REPORT
    # -------------------------
    def generate_report(self, city):
        data = self.cities[city]

        models = set()
        for block in data["scores"].values():
            models.update(block.keys())

        if not models:
            return f"⚠️ {city}: collecting model data..."

        ranked = [(m, self.compute_score(city, m)) for m in models]
        ranked.sort(key=lambda x: x[1], reverse=True)

        regime = self.detect_regime(city)
        signal, conf = self.generate_signal(ranked)

        out = []
        out.append("=" * 60)
        out.append(f"🏙 CITY REPORT: {city.upper()}")
        out.append(f"🌪 REGIME: {regime}")
        out.append(f"📊 CONFIDENCE: {conf}")
        out.append("")
        out.append("🏆 TOP MODELS:")

        for i, (m, s) in enumerate(ranked[:5], 1):
            out.append(f"{i}. {m} → {round(s, 3)}")

        out.append("")
        out.append(f"🎯 SIGNAL: {signal}")
        out.append("=" * 60)

        return "\n".join(out)

    # -------------------------
    # REPORT LOOP
    # -------------------------
    def maybe_report(self):
        now = time.time()

        for city, data in self.cities.items():

            has_temps = len(data["temps"]) >= 3
            has_scores = any(len(v) > 0 for v in data["scores"].values())

            if not has_temps:
                if now - data["last_report"] > 60:
                    print(f"⚠️ {city}: warming up (temps only)", flush=True)
                    data["last_report"] = now
                continue

            if not has_scores:
                if now - data["last_report"] > 60:
                    print(f"⚠️ {city}: warming up (waiting for scores)", flush=True)
                    data["last_report"] = now
                continue

            if now - data["last_report"] > 60:
                print(self.generate_report(city), flush=True)
                data["last_report"] = now
