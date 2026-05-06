import vectorbt as vbt
import pandas as pd
import numpy as np

# Parameters - Define ranges for optimization
ema_windows = [5, 9, 12, 15, 20]      # Test multiple EMA periods
sma_windows = [20, 30, 50, 100]       # Test multiple SMA periods  
vol_windows = [10, 20, 30]            # Test multiple volume lookback periods

ticker = 'AROC'
start = '2024-01-01'
end = '2026-05-04'

# Load data from local database
data = DataService.get_ohlcv_data(ticker, start, end)

# Get price and volume data
close = data['Close']
volume = data['Volume']

# Calculate indicators - vectorbt will create all parameter combinations (grid)
ema = vbt.MA.run(close, window=ema_windows, ewm=True)
sma = vbt.MA.run(close, window=sma_windows)
vol_ma = vbt.MA.run(volume, window=vol_windows)

# Generate signals - automatically broadcasts across all parameter combinations
# Shape will be: (n_timestamps, n_ema_windows × n_sma_windows × n_vol_windows)
entries = ema.ma_above(sma.ma) & (volume > vol_ma.ma)
exits = ema.ma_below(sma.ma) | (volume < vol_ma.ma)

# Create portfolio - now contains multiple columns (one per parameter combination)
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

# === Optimization Results Analysis ===
print(f"Total combinations tested: {pf.wrapper.shape[1]}")
print("-" * 50)

# Get performance metrics for all combinations
total_returns = pf.total_return()
sharpe_ratios = pf.sharpe_ratio()

# Find best combination by total return
best_idx = total_returns.idxmax()
best_return = total_returns.max()

print(f"Best Total Return: {best_return:.2%}")
print(f"Best Sharpe Ratio: {sharpe_ratios[best_idx]:.2f}")
print(f"Best Parameter Index: {best_idx}")

# Extract parameter values for the best combination
param_names = pf.split_param_names
param_values = pf.split_param_values[best_idx]

print(f"\nOptimal Parameters:")
for name, value in zip(param_names, param_values):
    print(f"  {name}: {value}")

# Display all results as DataFrame
results_df = pd.DataFrame({
    'Total_Return': total_returns,
    'Sharpe_Ratio': sharpe_ratios,
    'Max_Drawdown': pf.max_drawdown()
})

# Sort by return and display top 10
print("\nTop 10 Parameter Combinations:")
print(results_df.sort_values('Total_Return', ascending=False).head(10).to_string())

# Optional: Plot heatmap for 2 parameters (e.g., EMA vs SMA)
if len(ema_windows) > 1 and len(sma_windows) > 1:
    # Reshape returns for heatmap (taking first vol_window value as slice)
    returns_matrix = total_returns.values.reshape(len(ema_windows), len(sma_windows), len(vol_windows))
    returns_df = pd.DataFrame(
        returns_matrix[:, :, 0],  # First vol_window combination
        index=[f'EMA_{w}' for w in ema_windows],
        columns=[f'SMA_{w}' for w in sma_windows]
    )
    print("\nReturns Matrix (EMA vs SMA) for first Vol MA window:")
    print(returns_df.round(4))