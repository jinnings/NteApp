# ✅ Pullback runners every 2 min
if now - strategy.runner_alert_time > 120:

    runners = strategy.get_runners()

    if runners:
        msg = "📈 TODAY'S RUNNERS (PULLBACK ENTRY ✅)\n\n"

        for i, stock in enumerate(runners, 1):
            arrow = "🟢 BUY" if stock["direction"] == "BUY" else "🔴 SELL"

            msg += (
                f"{i}. {stock['symbol']}\n"
                f"{arrow} | Pullback ₹{stock['price']}\n"
                f"Change: {stock['change']}%\n\n"
            )

        send_alert(msg)

    else:
        send_alert("⚠️ No pullback runners available")

    strategy.runner_alert_time = now
``