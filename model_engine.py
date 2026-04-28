import time
from collections import defaultdict

class ModelEngine:
    def __init__(self):
        self.cities = defaultdict(lambda: {
            "temps": [],
            "forecasts": [],
            "scores": {
                "overall": {},
                "day_ahead": {},
                "day_of": {}
            },
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
                self.cities[city]["temps"] = self.cities[city]["temps"][-20:]
            except:
                pass

    # -------------------------
    # FORECASTS
    # -------------------------
    def process_forecast(self, msg):
        city = msg.get("slug")
        data = msg.get("forecasts", [])

        if city and data:
            self.cities[city]["forecasts"] = data

    # -------------------------
    # ORACLE SCORES
    # -------------------------
    def process_scores(self, msg):
        city = msg.get("slug")

        if not city:
            return

        overall = msg.get("overall", {}).get("scores", [])
        day_ahead = msg.get("day_ahead", {}).get("scores", [])
        day_of = msg.get("day_of", {}).get("scores", [])

        def parse(scores):
            return {
                s.get("model"): s.get("score")
                for s in scores
                if s.get("model") and s.get("score") is not None
            }

        self.cities[city]["scores"]["overall"] = parse(overall)
        self.cities[city]["scores"]["day_ahead"] = parse(day_ahead)
        self.cities[city]["scores"]["day_of"] = parse(day_of)

    # -------------------------
    # WEATHER EVENTS (SAFE NO-OP)
    # -------------------------
    def process_weather_event(self, msg):
        pass

    # -------------------------
    # MAIN REPORT ENGINE
    # -------------------------
    def generate_report(self, city):
        data = self.cities[city]

        scores = data["scores"]
        temps = data["temps"]

        combined = defaultdict(list)

        # merge all score types
        for mode in ["overall", "day_ahead", "day_of"]:
            for model, score in scores[mode].items():
                combined[model].append(score)

        if not combined:
            return f"⚠️ {city}: no model data yet"

        # average score per model
        ranked = []
        for model, vals in combined.items():
            avg = sum(vals) / len(vals)
            ranked.append((model, avg))

        ranked.sort(key=lambda x: x[1], reverse=True)

        top5 = ranked[:5]
        best_model = top5[0][0]

        # confidence
        confidence = "LOW"
        if len(ranked) >= 5:
            confidence = "MEDIUM"
        if len(ranked) >= 10:
            confidence = "HIGH"

        # trend (basic)
        trend = "STABLE"
        if len(temps) >= 5:
            if temps[-1] > temps[0]:
                trend = "WARMING"
            elif temps[-1] < temps[0]:
                trend = "COOLING"

        # build output
        lines = []
        lines.append("============================================================")
        lines.append(f"🏙 CITY REPORT: {city.upper()}")
        lines.append("------------------------------------------------------------")
        lines.append(f"🌡 Trend: {trend}")
        lines.append(f"📊 Confidence: {confidence}")
        lines.append("")
        lines.append("🏆 Top Models:")

        for i, (model, score) in enumerate(top5, 1):
            lines.append(f"{i}. {model} → {round(score, 3)}")

        lines.append("")
        lines.append(f"✅ BEST MODEL RIGHT NOW: {best_model}")
        lines.append("============================================================")

        return "\n".join(lines)

    # -------------------------
    # AUTO REPORT LOOP
    # -------------------------
    def maybe_report(self):
        now = time.time()

        for city in self.cities:
            if now - self.cities[city]["last_report"] > 60:
                print(self.generate_report(city), flush=True)
                self.cities[city]["last_report"] = now
