import requests
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID  # ✅ IMPORTANT

def send_alert(message):
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
        print("Telegram Error:", e)