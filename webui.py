from flask import Flask, render_template, jsonify
import json
import os

app = Flask(__name__)

LOG_FILE = "alerts_log.json"


def load_alerts():
    if not os.path.exists(LOG_FILE):
        return []

    try:
        with open(LOG_FILE, "r") as f:
            return json.load(f)[::-1]  # latest first
    except:
        return []


@app.route("/")
def dashboard():
    alerts = load_alerts()
    return render_template("dashboard.html", alerts=alerts)


@app.route("/api/alerts")
def api_alerts():
    return jsonify(load_alerts())


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)