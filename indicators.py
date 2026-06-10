import pandas as pd
from ta.momentum import RSIIndicator

def calculate_rsi(prices):
    series = pd.Series(prices)
    rsi = RSIIndicator(series, window=14).rsi()
    return rsi.iloc[-1]


def calculate_vwap(prices, volumes):
    pv = sum(p * v for p, v in zip(prices, volumes))
    total_volume = sum(volumes)
    if total_volume == 0:
        return prices[-1]
    return pv / total_volume