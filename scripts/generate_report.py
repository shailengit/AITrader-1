"""Generate a detailed HTML report from backtest JSON data."""
import json
import os
from datetime import datetime

REPORT_DIR = os.path.join(os.path.dirname(__file__), "..", "docs", "reports")

def load_json(name):
    with open(os.path.join(REPORT_DIR, name)) as f:
        return json.load(f)

def fmt_dollar(v):
    if v >= 0:
        return f"${v:,.2f}"
    return f"-${abs(v):,.2f}"

def fmt_pct(v):
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.2f}%"

def build_html():
    equity = load_json("daily_equity.json")
    trades = load_json("trades.json")
    summary = load_json("summary.json")

    # Compute CAGR
    start_val = summary["initial_capital"]
    end_val = summary["final_portfolio"]
    first_date = equity[0]["date"]
    last_date = equity[-1]["date"]
    years = (datetime.strptime(last_date, "%Y-%m-%d") - datetime.strptime(first_date, "%Y-%m-%d")).days / 365.25
    cagr = ((end_val / start_val) ** (1 / years) - 1) * 100

    # Build equity curve data points for chart
    eq_points = "".join(
        f"{{x:{i},y:{d['value']:.2f},date:'{d['date']}',cash:{d['cash']:.2f},holdings:{d['holdings']:.2f},n:{d['n_holdings']}}},"
        for i, d in enumerate(equity)
    )

    # Monthly returns
    eq_df = [(d["date"], d["value"]) for d in equity]
    monthly_map = {}
    for date_str, val in eq_df:
        ym = date_str[:7]
        monthly_map[ym] = val
    monthly_returns = []
    prev_val = None
    for ym in sorted(monthly_map.keys()):
        v = monthly_map[ym]
        if prev_val is not None:
            ret = (v - prev_val) / prev_val * 100
            monthly_returns.append({"month": ym, "return": round(ret, 2)})
        prev_val = v

    mr_rows = "".join(
        f"<tr><td>{m['month']}</td><td class={'green' if m['return']>=0 else 'red'}>{fmt_pct(m['return'])}</td></tr>"
        for m in monthly_returns[-36:]  # Last 36 months
    )

    # Sell trades table
    sell_trades = [t for t in trades if t["side"] == "SELL"]
    sell_trades.sort(key=lambda t: t["exit_date"])

    tr_rows = "".join(
        f"<tr>"
        f"<td>{t['ticker']}</td>"
        f"<td>{t['entry_date']}</td>"
        f"<td>{t['exit_date']}</td>"
        f"<td>{t['holding_days']}d</td>"
        f"<td>{fmt_dollar(t['entry_price'])}</td>"
        f"<td>{fmt_dollar(t['exit_price'])}</td>"
        f"<td class={'green' if t['return_pct']>=0 else 'red'}>{fmt_pct(t['return_pct'])}</td>"
        f"<td class={'green' if t['pnl_dollars']>=0 else 'red'}>{fmt_dollar(t['pnl_dollars'])}</td>"
        f"<td>{t['exit_reason']}</td>"
        f"</tr>\n"
        for t in sell_trades
    )

    # Exit reason breakdown
    exit_reasons = summary.get("exit_reasons", {})
    exit_rows = "".join(
        f"<tr><td>{r}</td><td>{c}</td><td>{c/len(sell_trades)*100:.1f}%</td></tr>"
        for r, c in sorted(exit_reasons.items(), key=lambda x: -x[1])
    )

    # Top/bottom trades
    sorted_by_ret = sorted(sell_trades, key=lambda t: t["return_pct"], reverse=True)
    top5 = sorted_by_ret[:5]
    bottom5 = sorted_by_ret[-5:]

    def trade_row(t):
        cls = "green" if t["return_pct"] >= 0 else "red"
        return (
            f"<tr>"
            f"<td>{t['ticker']}</td>"
            f"<td>{t['entry_date']}</td>"
            f"<td>{t['exit_date']}</td>"
            f"<td>{t['holding_days']}d</td>"
            f"<td class={cls}>{fmt_pct(t['return_pct'])}</td>"
            f"<td class={cls}>{fmt_dollar(t['pnl_dollars'])}</td>"
            f"<td>{t['exit_reason']}</td>"
            f"</tr>"
        )

    top5_rows = "".join(trade_row(t) for t in top5)
    bottom5_rows = "".join(trade_row(t) for t in bottom5)

    # Holdings over time chart data
    holdings_points = "".join(
        f"{{x:{i},y:{d['n_holdings']},date:'{d['date']}}},"
        for i, d in enumerate(equity)
    )

    # Drawdown
    peak = start_val
    dd_points_list = []
    for d in equity:
        peak = max(peak, d["value"])
        dd = (d["value"] - peak) / peak * 100
        dd_points_list.append(dd)
    max_dd = min(dd_points_list)
    dd_points = "".join(
        f"{{x:{i},y:{dd:.2f},date:'{equity[i]['date']}}},"
        for i, dd in enumerate(dd_points_list)
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Daily Golden Cross Rotation — Detailed Report</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f1117; color: #e1e4e8; padding: 24px; }}
.container {{ max-width: 1400px; margin: 0 auto; }}
h1 {{ font-size: 28px; margin-bottom: 8px; color: #f0f6fc; }}
h2 {{ font-size: 20px; margin: 32px 0 16px; color: #f0f6fc; border-bottom: 1px solid #30363d; padding-bottom: 8px; }}
h3 {{ font-size: 16px; margin: 20px 0 12px; color: #c9d1d9; }}
.stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin: 20px 0; }}
.stat-card {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px; }}
.stat-label {{ font-size: 12px; color: #8b949e; text-transform: uppercase; letter-spacing: 0.5px; }}
.stat-value {{ font-size: 24px; font-weight: 700; margin-top: 4px; }}
.stat-value.green {{ color: #3fb950; }}
.stat-value.red {{ color: #f85149; }}
.chart-container {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px; margin: 16px 0; }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
th {{ text-align: left; padding: 8px 12px; background: #161b22; border-bottom: 2px solid #30363d; color: #8b949e; font-weight: 600; position: sticky; top: 0; }}
td {{ padding: 6px 12px; border-bottom: 1px solid #21262d; }}
tr:hover {{ background: #1c2128; }}
.green {{ color: #3fb950; }}
.red {{ color: #f85149; }}
.table-wrap {{ overflow-x: auto; max-height: 600px; overflow-y: auto; border: 1px solid #30363d; border-radius: 8px; }}
.metrics-row {{ display: flex; gap: 24px; flex-wrap: wrap; margin: 8px 0; }}
.metric {{ font-size: 14px; }}
.metric-label {{ color: #8b949e; }}
.metric-value {{ font-weight: 600; }}
</style>
</head>
<body>
<div class="container">
<h1>📈 Daily Golden Cross Rotation Strategy</h1>
<p style="color:#8b949e;margin-bottom:24px;">{first_date} → {last_date} ({years:.1f} years) | Take Profit: 50% | Trailing Stop: 20% | Min Hold: 10d | Max 2/sector</p>

<div class="stats-grid">
<div class="stat-card"><div class="stat-label">Total Return</div><div class="stat-value green">{fmt_pct(summary['total_return_pct'])}</div></div>
<div class="stat-card"><div class="stat-label">CAGR</div><div class="stat-value green">{fmt_pct(cagr)}</div></div>
<div class="stat-card"><div class="stat-label">SPY Return</div><div class="stat-value green">{fmt_pct(summary.get('spy_return_pct', 0))}</div></div>
<div class="stat-card"><div class="stat-label">Alpha</div><div class="stat-value green">{fmt_pct(summary['total_return_pct'] - summary.get('spy_return_pct', 0))}</div></div>
<div class="stat-card"><div class="stat-label">Final Portfolio</div><div class="stat-value green">{fmt_dollar(summary['final_portfolio'])}</div></div>
<div class="stat-card"><div class="stat-label">Max Drawdown</div><div class="stat-value red">{fmt_pct(max_dd)}</div></div>
<div class="stat-card"><div class="stat-label">Win Rate</div><div class="stat-value">{summary['win_rate']}%</div></div>
<div class="stat-card"><div class="stat-label">Profit Factor</div><div class="stat-value">{summary['profit_factor']}</div></div>
<div class="stat-card"><div class="stat-label">Total Trades</div><div class="stat-value">{summary['total_trades']}</div></div>
<div class="stat-card"><div class="stat-label">Avg Winner</div><div class="stat-value green">{fmt_dollar(summary['avg_winner'])}</div></div>
<div class="stat-card"><div class="stat-label">Avg Loser</div><div class="stat-value red">{fmt_dollar(summary['avg_loser'])}</div></div>
</div>

<div class="metrics-row">
<span class="metric"><span class="metric-label">Best Month: </span><span class="metric-value green">{fmt_pct(summary.get('best_month', 0))}</span></span>
<span class="metric"><span class="metric-label">Worst Month: </span><span class="metric-value red">{fmt_pct(summary.get('worst_month', 0))}</span></span>
<span class="metric"><span class="metric-label">Avg Month: </span><span class="metric-value">{fmt_pct(summary.get('avg_month', 0))}</span></span>
<span class="metric"><span class="metric-label">Positive Months: </span><span class="metric-value">{summary.get('positive_months', 'N/A')}</span></span>
</div>

<div class="chart-container">
<h3>Equity Curve</h3>
<canvas id="equityChart" height="80"></canvas>
</div>

<div class="chart-container">
<h3>Drawdown</h3>
<canvas id="ddChart" height="60"></canvas>
</div>

<div class="chart-container">
<h3>Holdings Over Time</h3>
<canvas id="holdingsChart" height="50"></canvas>
</div>

<h2>📊 Exit Reason Breakdown</h2>
<div class="table-wrap" style="max-height:none">
<table>
<thead><tr><th>Exit Reason</th><th>Count</th><th>% of Total</th></tr></thead>
<tbody>{exit_rows}</tbody>
</table>
</div>

<h2>🏆 Top 5 Winners</h2>
<div class="table-wrap" style="max-height:none">
<table>
<thead><tr><th>Ticker</th><th>Entry</th><th>Exit</th><th>Held</th><th>Return</th><th>P&L</th><th>Reason</th></tr></thead>
<tbody>{top5_rows}</tbody>
</table>
</div>

<h2>💀 Bottom 5 Losers</h2>
<div class="table-wrap" style="max-height:none">
<table>
<thead><tr><th>Ticker</th><th>Entry</th><th>Exit</th><th>Held</th><th>Return</th><th>P&L</th><th>Reason</th></tr></thead>
<tbody>{bottom5_rows}</tbody>
</table>
</div>

<h2>📅 Monthly Returns (Last 36 Months)</h2>
<div class="table-wrap" style="max-height:none">
<table>
<thead><tr><th>Month</th><th>Return</th></tr></thead>
<tbody>{mr_rows}</tbody>
</table>
</div>

<h2>📋 All Trades ({len(sell_trades)})</h2>
<div class="table-wrap">
<table>
<thead><tr><th>Ticker</th><th>Entry Date</th><th>Exit Date</th><th>Held</th><th>Entry Price</th><th>Exit Price</th><th>Return</th><th>P&L</th><th>Exit Reason</th></tr></thead>
<tbody>{tr_rows}</tbody>
</table>
</div>

</div>

<script>
const colors = {{
    green: '#3fb950',
    red: '#f85149',
    text: '#8b949e',
    grid: '#21262d',
}};

new Chart(document.getElementById('equityChart'), {{
    type: 'line',
    data: {{
        datasets: [{{
            label: 'Portfolio Value',
            data: [{eq_points}],
            borderColor: '#58a6ff',
            backgroundColor: 'rgba(88,166,255,0.1)',
            fill: true,
            tension: 0.1,
            pointRadius: 0,
            borderWidth: 1.5,
            parsing: {{ xAxisKey: 'x', yAxisKey: 'y' }}
        }}]
    }},
    options: {{
        responsive: true,
        maintainAspectRatio: false,
        plugins: {{ legend: {{ display: false }} }},
        scales: {{
            x: {{ display: false }},
            y: {{
                grid: {{ color: colors.grid }},
                ticks: {{ callback: v => '$' + v.toLocaleString() }}
            }}
        }}
    }}
}});

new Chart(document.getElementById('ddChart'), {{
    type: 'line',
    data: {{
        datasets: [{{
            label: 'Drawdown',
            data: [{dd_points}],
            borderColor: '#f85149',
            backgroundColor: 'rgba(248,81,73,0.15)',
            fill: true,
            tension: 0.1,
            pointRadius: 0,
            borderWidth: 1.5,
            parsing: {{ xAxisKey: 'x', yAxisKey: 'y' }}
        }}]
    }},
    options: {{
        responsive: true,
        maintainAspectRatio: false,
        plugins: {{ legend: {{ display: false }} }},
        scales: {{
            x: {{ display: false }},
            y: {{
                grid: {{ color: colors.grid }},
                ticks: {{ callback: v => v.toFixed(1) + '%' }}
            }}
        }}
    }}
}});

new Chart(document.getElementById('holdingsChart'), {{
    type: 'line',
    data: {{
        datasets: [{{
            label: 'Holdings',
            data: [{holdings_points}],
            borderColor: '#d2a8ff',
            backgroundColor: 'rgba(210,168,255,0.1)',
            fill: true,
            tension: 0.3,
            pointRadius: 0,
            borderWidth: 1.5,
            parsing: {{ xAxisKey: 'x', yAxisKey: 'y' }}
        }}]
    }},
    options: {{
        responsive: true,
        maintainAspectRatio: false,
        plugins: {{ legend: {{ display: false }} }},
        scales: {{
            x: {{ display: false }},
            y: {{
                grid: {{ color: colors.grid }},
                min: 0,
                max: 6,
                ticks: {{ stepSize: 1 }}
            }}
        }}
    }}
}});
</script>
</body>
</html>"""

    out_path = os.path.join(REPORT_DIR, "daily_golden_cross_report.html")
    with open(out_path, "w") as f:
        f.write(html)
    print(f"✅ Report written to {out_path}")

if __name__ == "__main__":
    build_html()
