import time
from collections import defaultdict, deque


class ModelEngineV3:
    """
    Tiered live intelligence engine:
    - Tier 1: cold start (temps only)
    - Tier 2: emerging intelligence (temps + forecasts/events)
    - Tier 3: full ranking (oracle scores)
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
            "errors": defaultdict(lambda: deque(maxlen=30)),
            "weather_events": deque(maxlen=30),
            "last_report": 0
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

        # validate forecasts when new truth arrives
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
    # FORECAST VALIDATION
    # -------------------------
    def validate_forecasts(self, city, actual):
        forecasts = self.cities[city]["forecasts"]

        for model, pred in forecasts.items():
            try:
                error = abs(pred - actual)
                self.cities[city]["errors"][model].append(error)
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
        penalty = (sum(err_list) / len(err_list)) * 0.05 if err_list else 0

        return base - penalty

    # -------------------------
    # REGIME DETECTION
    # -------------------------
    def detect_regime(self, city):
        temps = list(self.cities[city]["temps"])
        events = self.cities[city]["weather_events"]

        if len(events) >= 5:
            return "STORM-RISK"

        if len(temps) < 3:
            return "COLD-START"

        delta = temps[-1] - temps[0]

        if abs(delta) < 1:
            return "STABLE"
        elif abs(delta) < 3:
            return "TRENDING"
        else:
            return "VOLATILE"

    # -------------------------
    # SIGNAL ENGINE
    # -------------------------
    def generate_signal(self, ranked):
        if not ranked:
            return "NO TRADE", "LOW"

        best, score = ranked[0]

        if len(ranked) >= 5 and score > 0.7:
            return f"STRONG SIGNAL: {best}", "HIGH"
        elif len(ranked) >= 3:
            return f"WEAK SIGNAL: {best}", "MEDIUM"

        return "NO TRADE", "LOW"

    # -------------------------
    # REPORT TIERS
    # -------------------------
    def tier1(self, city):
        temps = list(self.cities[city]["temps"])

        return "\n".join([
            "🟢 COLD START INTELLIGENCE",
            f"City: {city.upper()}",
            f"Temp: {temps[-1] if temps else 'N/A'}",
            f"Data points: {len(temps)}",
            "Status: collecting baseline signals"
        ])

    def tier2(self, city):
        temps = list(self.cities[city]["temps"])
        regime = self.detect_regime(city)

        return "\n".join([
            "🟡 EMERGING INTELLIGENCE",
            f"City: {city.upper()}",
            f"Temp: {temps[-1] if temps else 'N/A'}",
            f"Regime: {regime}",
            f"Weather events: {len(self.cities[city]['weather_events'])}"
        ])

    def tier3(self, city):
        data = self.cities[city]

        models = set()
        for d in data["scores"].values():
            models.update(d.keys())

        ranked = [(m, self.compute_score(city, m)) for m in models]
        ranked.sort(key=lambda x: x[1], reverse=True)

        regime = self.detect_regime(city)
        signal, conf = self.generate_signal(ranked)

        lines = [
            "🔴 FULL INTELLIGENCE REPORT",
            f"City: {city.upper()}",
            f"Regime: {regime}",
            f"Confidence: {conf}",
            "",
            "🏆 MODEL LEADERBOARD"
        ]

        for i, (m, s) in enumerate(ranked[:5], 1):
            lines.append(f"{i}. {m} → {round(s, 3)}")

        lines += ["", f"🎯 SIGNAL: {signal}"]

        return "\n".join(lines)

    # -------------------------
    # MASTER REPORT
    # -------------------------
    def generate_report(self, city):
        data = self.cities[city]

        temps = len(data["temps"])
        scores_exist = any(len(v) > 0 for v in data["scores"].values())

        if scores_exist:
            return self.tier3(city)

        if temps >= 5:
            return self.tier2(city)

        if temps >= 1:
            return self.tier1(city)

        return f"⚠️ {city}: waiting for data"

    # -------------------------
    # LOOP
    # -------------------------
    def maybe_report(self):
        now = time.time()

        for city in self.cities:
            data = self.cities[city]

            if now - data["last_report"] > 60:
                print(self.generate_report(city), flush=True)
                data["last_report"] = now
