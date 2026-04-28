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

        if not city or temp is None:
            return

        try:
            temp = float(temp)
        except:
            return

        data = self.cities[city]
        data["temps"].append(temp)
        data["temps"] = data["temps"][-50:]

        self._update_errors(city, temp)

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

            if not model or temp is None:
                continue

            try:
                data["forecasts"][model] = float(temp)
            except:
                continue

    # -------------------------
    # SCORES
    # -------------------------
    def process_scores(self, msg):
        city = msg.get("slug")
        if not city:
            return

        data = self.cities[city]

        def safe(obj):
            out = {}
            if isinstance(obj, list):
                for x in obj:
                    if isinstance(x, dict):
                        m = x.get("model")
                        s = x.get("score")
                        if m and s is not None:
                            try:
                                out[m] = float(s)
                            except:
                                pass
            return out

        data["scores"]["overall"] = safe(msg.get("overall", {}).get("scores", []))
        data["scores"]["day_ahead"] = safe(msg.get("day_ahead", {}).get("scores", []))
        data["scores"]["day_of"] = safe(msg.get("day_of", {}).get("scores", []))

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
    # ERROR TRACKING
    # -------------------------
    def _update_errors(self, city, actual):
        data = self.cities[city]

        for model, pred in data["forecasts"].items():
            try:
                err = abs(float(pred) - float(actual))
                data["errors"][model].append(err)
                data["errors"][model] = data["errors"][model][-30:]
            except:
                continue

    # -------------------------
    # SCORING (SAFE)
    # -------------------------
    def compute_score(self, city, model):
        data = self.cities[city]

        s = data["scores"]
        e = data["errors"]

        base = (
            s["day_of"].get(model, 0) * 0.5 +
            s["day_ahead"].get(model, 0) * 0.3 +
            s["overall"].get(model, 0) * 0.2
        )

        errs = e.get(model, [])
        penalty = (sum(errs) / len(errs)) * 0.05 if errs else 0

        return base - penalty

    # -------------------------
    # REGIME
    # -------------------------
    def detect_regime(self, city):
        data = self.cities[city]
        temps = data["temps"]
        events = data["weather_events"]

        if len(events) > 5:
            return "STORM"

        if len(temps) < 2:
            return "INSUFFICIENT"

        delta = temps[-1] - temps[0]

        if abs(delta) < 1:
            return "STABLE"
        if abs(delta) < 3:
            return "TRANSITION"
        return "VOLATILE"

    # -------------------------
    # SIGNAL
    # -------------------------
    def generate_signal(self, ranked):
        if not ranked:
            return "NO MODELS", "LOW"

        best, score = ranked[0]

        if score > 0.7:
            return f"STRONG LEADER: {best}", "HIGH"
        if score > 0.4:
            return f"MODERATE LEADER: {best}", "MEDIUM"
        return f"WEAK LEADER: {best}", "LOW"

    # -------------------------
    # REPORT (ALWAYS OUTPUTS)
    # -------------------------
    def generate_report(self, city):
        data = self.cities[city]

        temps = data["temps"]

        models = set()
        for group in data["scores"].values():
            models.update(group.keys())

        ranked = []
        if models:
            ranked = [(m, self.compute_score(city, m)) for m in models]
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
        lines.append(f"📊 Signal: {signal} ({conf})")

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
    # REPORT LOOP (FIXED)
    # -------------------------
    def maybe_report(self):
        now = time.time()

        for city, data in self.cities.items():
            if now - data["last_report"] < 60:
                continue

            print(self.generate_report(city), flush=True)
            data["last_report"] = now
