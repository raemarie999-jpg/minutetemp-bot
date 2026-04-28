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
    # OBSERVATIONS
    # -------------------------
    def process_observation(self, msg):
        city = msg.get("slug")
        temp = msg.get("temperature_f")

        if not city:
            return

        try:
            if temp is None:
                return

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

        data = self.cities[city]

        for f in forecasts:
            model = f.get("model")
            temp = f.get("temp_f")

            if not model:
                continue

            try:
                if temp is None:
                    continue
                data["forecasts"][model] = float(temp)
            except:
                continue

    # -------------------------
    # ORACLE SCORES (SAFE PARSER)
    # -------------------------
    def process_scores(self, msg):
        city = msg.get("slug")
        if not city:
            return

        data = self.cities[city]

        def safe_parse(obj):
            if not isinstance(obj, list):
                return {}
            out = {}
            for item in obj:
                if not isinstance(item, dict):
                    continue
                m = item.get("model")
                s = item.get("score")
                if m is None or s is None:
                    continue
                try:
                    out[m] = float(s)
                except:
                    continue
            return out

        # Flexible extraction (handles unknown API shapes)
        data["scores"]["overall"] = safe_parse(
            msg.get("overall", {}).get("scores", [])
        )

        data["scores"]["day_ahead"] = safe_parse(
            msg.get("day_ahead", {}).get("scores", [])
        )

        data["scores"]["day_of"] = safe_parse(
            msg.get("day_of", {}).get("scores", [])
        )

    # -------------------------
    # WEATHER EVENTS
    # -------------------------
    def process_weather_event(self, msg):
        city = msg.get("slug")
        summary = msg.get("summary", "")

        if not city:
            return

        data = self.cities[city]
        data["weather_events"].append(summary)
        data["weather_events"] = data["weather_events"][-30:]

    # -------------------------
    # VALIDATION
    # -------------------------
    def validate_forecasts(self, city, actual_temp):
        data = self.cities[city]

        for model, predicted in data["forecasts"].items():
            try:
                error = abs(float(predicted) - float(actual_temp))
                data["errors"][model].append(error)
                data["errors"][model] = data["errors"][model][-30:]
            except:
                continue

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
    # REGIME DETECTION (ROBUST)
    # -------------------------
    def detect_regime(self, city):
        data = self.cities[city]
        temps = data["temps"]
        events = data["weather_events"]

        if len(events) >= 5:
            return "STORMY"

        if len(temps) < 3:
            return "UNKNOWN"

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
            return "NO DATA", "LOW"

        best, score = ranked[0]

        if score > 0.7:
            return f"STRONG LEADER: {best}", "HIGH"
        elif score > 0.4:
            return f"MODERATE LEADER: {best}", "MEDIUM"
        else:
            return f"WEAK LEADER: {best}", "LOW"

    # -------------------------
    # REPORT (ALWAYS OUTPUTS)
    # -------------------------
    def generate_report(self, city):
        data = self.cities[city]

        temps = data["temps"]

        all_models = set()
        for group in data["scores"].values():
            if isinstance(group, dict):
                all_models.update(group.keys())

        ranked = []
        if all_models:
            ranked = [(m, self.compute_score(city, m)) for m in all_models]
            ranked.sort(key=lambda x: x[1], reverse=True)

        regime = self.detect_regime(city)
        signal, conf = self.generate_signal(ranked)

        lines = []
        lines.append("=" * 60)
        lines.append(f"🏙 CITY INTELLIGENCE: {city.upper()}")
        lines.append("-" * 60)

        if temps:
            lines.append(f"🌡 Temps: {len(temps)} | latest={temps[-1]:.1f}")
        else:
            lines.append("🌡 Temps: NO DATA")

        lines.append(f"🌪 Regime: {regime}")
        lines.append(f"📊 Signal Confidence: {conf}")

        lines.append("")
        lines.append("🏆 TOP MODELS:")

        if ranked:
            for i, (m, s) in enumerate(ranked[:5], 1):
                lines.append(f"{i}. {m} → {round(s, 3)}")
        else:
            lines.append("No model data yet (stream warming)")

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

            if now - data["last_report"] < 60:
                continue

            print(self.generate_report(city), flush=True)
            data["last_report"] = now
