import vectorbt as vbt
import pandas as pd
import numpy as np

# Parameters
fast_ema_window = 2
slow_ema_window = 10

# Download data
ticker = 'CIEN'
start = '2026-02-07'
end = '2026-05-06'
data = DataService.get_ohlcv_data(ticker, start, end)
if data is None:
    raise ValueError(f"No data found for ticker '{ticker}' from {start} to {end}")

# Get price data
close = data.get('Close')

# Calculate EMAs using MA with ewm=True
fast_ema = vbt.MA.run(close, window=fast_ema_window, ewm=True)
slow_ema = vbt.MA.run(close, window=slow_ema_window, ewm=True)

# Generate signals using VBT methods
entries = fast_ema.ma_crossed_above(slow_ema.ma)
exits = fast_ema.ma_crossed_below(slow_ema.ma)

# Create portfolio with OHLC data
pf = vbt.Portfolio.from_signals(
    close,
    entries=entries,
    exits=exits,
    open=data.get('Open'),
    high=data.get('High'),
    low=data.get('Low'),
    freq='1d'
)

# Print stats
print(pf.stats())
print(f"\nTotal Return: {pf.total_return()}")