import os

API_KEY = os.getenv("MINUTETEMP_API_KEY")

CITIES = ["KMDW", "KDFW", "NYC"]

if not API_KEY:
    print("⚠️ WARNING: MINUTETEMP_API_KEY is missing")
