import requests
import time
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID  # ✅ IMPORTANT


def send_alert(message):
    # ✅ 1. ALWAYS PRINT TO CONSOLE (TEMP LOGGING)
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')

    print("\n===================================")
    print(f"[{timestamp}] 🚨 ALERT TRIGGERED")
    print(message.strip())
    print("===================================\n")

    # ✅ 2. KEEP TELEGRAM (UNCHANGED)
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    
    try:
        requests.post(
            url,
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message
            },
            verify=False  # ✅ to avoid SSL issue
        )

    except Exception as e:
        # ✅ 3. PRINT TELEGRAM ERROR (SO YOU KNOW)
        print("⚠️ Telegram Error:", e)