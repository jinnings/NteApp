from fastapi import FastAPI
import json

app = FastAPI()


@app.get("/alerts")
def get_alerts():
    try:
        with open("alerts_log.json", "r") as f:
            return json.load(f)
    except:
        return []