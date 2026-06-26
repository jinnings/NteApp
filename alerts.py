import requests
import time
import json
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

LOG_FILE = "alerts_log.json"
COOLDOWN_SECONDS = 300  # 5 minutes


def save_alert(message, symbol=None, direction=None, entry=None, sl=None, target=None, strategy_name=None):

    current_time = time.time()

    try:
        try:
            with open(LOG_FILE, "r") as f:
                data = json.load(f)
        except:
            data = []

        # ✅ ✅ SYSTEM ALERT (must be INSIDE function)
        if symbol is None:
            alert = {
                "time": time.strftime('%Y-%m-%d %H:%M:%S'),
                "message": message.strip(),
                "status": "INFO"
            }

            data.append(alert)
            data = data[-200:]

            with open(LOG_FILE, "w") as f:
                json.dump(data, f, indent=2)

            return  # ✅ VALID now

        # ✅ ✅ CHECK EXISTING TRADES
        for existing in data:

            if existing.get("symbol") != symbol:
                continue

            if existing.get("strategy") != strategy_name:
                continue

            status = existing.get("status")
            alert_time = existing.get("timestamp", 0)

            # ❌ Block if active
            if status == "OPEN":
                print(f"⛔ Skip {symbol} ({strategy_name}) → active trade exists")
                return

            # ❌ Block if cooldown running
            if current_time - alert_time < COOLDOWN_SECONDS:
                print(f"⏳ Cooldown active for {symbol} ({strategy_name})")
                return

        # ✅ ✅ ALLOW NEW TRADE
        alert = {
            "time": time.strftime('%Y-%m-%d %H:%M:%S'),
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

    # ✅ Telegram optional
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

        try:
            requests.post(url, data={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message
            })
        except Exception as e:
            print("Telegram error:", e)