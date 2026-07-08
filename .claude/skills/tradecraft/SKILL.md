# TradeCraft Natural Language Strategy Lab

Use this skill when the user wants to create, backtest, analyze, or save trading strategies using natural language.

## Workflow

### Creating a Strategy

1. Call `tradecraft strategy create "<description>" --tickers <list>`
2. Present the summary and generated code to the user
3. Ask if they want to backtest it

### Backtesting

1. Call `tradecraft strategy backtest <id>`
2. Present metrics: total_return, win_rate, sharpe_ratio, max_drawdown, n_trades
3. Offer multi-asset testing: `tradecraft strategy test-on <id> --tickers <list>`
4. Offer to save: `tradecraft strategy save <id> --name "<name>"`

### Lessons Learned (Code Quality)

Before generating strategy code, check for relevant lessons:
1. Read `~/.config/tradecraft/lessons.json`
2. If lessons exist with `count > 0` matching the context, include them in the generation prompt as "known pitfalls to avoid"
3. After a failed backtest, capture the error and store it:
   - `tradecraft lessons add --error "<error>" --fix "<fix>" --pattern "<name>"`

### Checking Performance

- `tradecraft coach kpis --period 90` — get KPI dashboard
- `tradecraft coach report --period 90` — get LLM critique
- `tradecraft coach trades list` — see recent trades

### Markov Learning Agent

- `tradecraft markov status` — check model health
- `tradecraft markov signal <ticker>` — get conviction signal

## Output Format

All commands support `--json` for machine-readable output. Parse the JSON to extract metrics and present them conversationally to the user.
