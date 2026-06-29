import requests
import time
import json
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
from datetime import datetime
import pytz

LOG_FILE = "alerts_log.json"
COOLDOWN_SECONDS = 300


# ✅ IST TIME
def get_ist_time():
    ist = pytz.timezone("Asia/Kolkata")
    return datetime.now(ist).strftime('%Y-%m-%d %H:%M:%S')


def save_alert(message, symbol=None, direction=None, entry=None, sl=None, target=None, strategy_name=None):
    current_time = time.time()

    try:
        try:
            with open(LOG_FILE, "r") as f:
                data = json.load(f)
        except:
            data = []

        # ✅ SYSTEM ALERT
        if symbol is None:
            alert = {
                "time": get_ist_time(),
                "message": message.strip(),
                "status": "INFO"
            }

            data.append(alert)
            data = data[-200:]

            with open(LOG_FILE, "w") as f:
                json.dump(data, f, indent=2)

            return

        # ✅ BLOCK DUPLICATES
        for existing in data:
            if existing.get("symbol") != symbol:
                continue
            if existing.get("strategy") != strategy_name:
                continue

            if existing.get("status") == "OPEN":
                return

            if current_time - existing.get("timestamp", 0) < COOLDOWN_SECONDS:
                return

        # ✅ NEW ALERT
        alert = {
            "time": get_ist_time(),   # ✅ IST
            "timestamp": current_time,
            "message": message.strip(),
            "symbol": symbol,
            "direction": direction,
            "entry": entry,
            "sl": sl,
            "target": target,
            "strategy": strategy_name,
            "status": "OPEN"
        }

        data.append(alert)
        data = data[-200:]

        with open(LOG_FILE, "w") as f:
            json.dump(data, f, indent=2)

    except Exception as e:
        print("Log error:", e)


def send_alert(message, symbol=None, direction=None, entry=None, sl=None, target=None, strategy_name=None):
    print("\nALERT:\n", message)

    save_alert(message, symbol, direction, entry, sl, target, strategy_name)

    # ✅ TELEGRAM
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            requests.post(url, data={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message
            })
        except Exception as e:
            print("Telegram error:", e)