# ✅ SYSTEM ALERT (no trading fields) → skip trading logic
if symbol is None:
    alert = {
        "time": time.strftime('%Y-%m-%d %H:%M:%S'),
        "message": message.strip(),
        "status": "INFO"
    }

    data.append(alert)

    with open(LOG_FILE, "w") as f:
        json.dump(data, f, indent=2)

    return
