import os

API_KEY = os.getenv("MINUTETEMP_API_KEY")

CITIES = ["chi", "dal", "nyc"]

if not API_KEY:
    print("⚠️ WARNING: MINUTETEMP_API_KEY is missing")
