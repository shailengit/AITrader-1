import vectorbt as vbt
import pandas as pd
import numpy as np

# Parameters - scalar values for single backtest (use ranges for optimization)
ema_window = 9          # EMA period
sma_window = 20         # SMA period
vol_window = 20         # Volume MA period

ticker = 'AROC'
start = '2024-01-01'
end = '2026-05-04'

# Load data from local database
data = DataService.get_ohlcv_data(ticker, start, end)
if data is None:
    raise ValueError(f"No data found for ticker '{ticker}' from {start} to {end}")

# Get price and volume data
close = data['Close']
volume = data['Volume']

# Calculate indicators with single parameters
ema = vbt.MA.run(close, window=ema_window, ewm=True)
sma = vbt.MA.run(close, window=sma_window)
vol_ma = vbt.MA.run(volume, window=vol_window)

# Generate signals - single column, safe to use operators
entries = ema.ma_above(sma.ma) & (volume > vol_ma.ma)
exits = ema.ma_below(sma.ma) | (volume < vol_ma.ma)

# Create portfolio
pf = vbt.Portfolio.from_signals(
    close,
    entries=entries,
    exits=exits,
    open=data['Open'],
    high=data['High'],
    low=data['Low'],
    direction='longonly',
    freq='1d'
)

# === Results Analysis ===
n_combos = pf.wrapper.shape[1] if len(pf.wrapper.shape) > 1 else 1
print(f"Parameter set combinations tested: {n_combos}")
print("-" * 50)

# Get performance metrics
stats = pf.stats()
print(stats.to_string())

# Key metrics
total_return = pf.total_return()
sharpe_ratio = pf.sharpe_ratio()
max_dd = pf.max_drawdown()

print(f"\nTotal Return: {total_return:.2%}")
print(f"Sharpe Ratio: {sharpe_ratio:.2f}")
print(f"Max Drawdown: {max_dd:.2%}")

# Trade analysis
trades = pf.trades
if len(trades) > 0:
    print(f"\nTrade Statistics:")
    print(f"  Total Trades: {len(trades)}")
    print(f"  Win Rate: {trades.win_rate():.2%}")
    print(f"  Avg Win: {trades.avg_win():.2%}")
    print(f"  Avg Loss: {trades.avg_loss():.2%}")
    print(f"  Best Trade: {trades.max_win():.2%}")
    print(f"  Worst Trade: {trades.max_loss():.2%}")
else:
    print("\nNo trades were generated. Check signal logic.")
    print(f"  Entries True: {entries.sum().item()}")
    print(f"  Exits True: {exits.sum().item()}")