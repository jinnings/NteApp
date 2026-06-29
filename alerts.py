import requests
 jsonimport time
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
from datetime import datetime
import pytz

LOG_FILE = "alerts_log.json"

def get_ist_time():
    ist = pytz.timezone("Asia/Kolkata")
    return datetime.now(ist).strftime('%Y-%m-%d %H:%M:%S')


def save_alert(message, symbol=None, direction=None, entry=None, sl=None, target=None,
               strategy=None, confidence=None, trend=None, risk=None):

    try:
        try:
            with open(LOG_FILE, "r") as f:
                data = json.load(f)
        except:
            data = []

        alert = {
            "time": get_ist_time(),
            "message": message,
            "symbol": symbol,
            "direction": direction,
            "entry": entry,
            "sl": sl,
            "target": target,
            "strategy": strategy,
            "confidence": confidence,
            "trend": trend,
            "risk": risk
        }

        data.append(alert)
        data = data[-200:]

        with open(LOG_FILE, "w") as f:
            json.dump(data, f, indent=2)

    except Exception as e:
        print(e)


def send_alert(message, symbol=None, direction=None, entry=None, sl=None, target=None,
               strategy=None, confidence=None, trend=None, risk=None):

    print(message)

    save_alert(message, symbol, direction, entry, sl, target,
               strategy, confidence, trend, risk)

    if TELEGRAM_TOKEN:
        try:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                data={"chat_id": TELEGRAM_CHAT_ID, "text": message}
            )
        except Exception as e:
            print("Telegram error:", e)
