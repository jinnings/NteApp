if current_price >= day_high:
    signal = "BREAKOUT"

elif current_price >= day_high * 0.97:
    signal = "PULLBACK READY"

else:
    return