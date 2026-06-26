import requests
import time
import json
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

LOG_FILE = "alerts_log.json"

def save_alert(message):
    alert = {
        "time": time.strftime('%Y-%m-%d %H:%M:%S'),
        "message": message.strip()
    }

    try:
        try:
            with open(LOG_FILE, "r") as f:
                data = json.load(f)
        except:
            data = []

        data.append(alert)
        data = data[-200:]

        with open(LOG_FILE, "w") as f:
            json.dump(data, f, indent=2)

    except Exception as e:
        print("Log error:", e)

def send_alert(message):
    print("\nALERT:\n", message)
    save_alert(message)

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    try:
        requests.post(url, data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message
        })
    except Exception as e:
        print("Telegram error:", e)
``