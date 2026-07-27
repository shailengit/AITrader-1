"""
Run Viewer — Generate browsable HTML for all 100 validation runs
================================================================
Creates an HTML page with all runs, sortable by any metric,
with expandable trade details per run.

Usage:
  cd backend && ./venv/bin/python ../strategies/generate_run_viewer.py
"""

import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
JSON_PATH = BASE_DIR / "validation_detailed_crisis.json"
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "docs" / "reports" / "run_viewer.html"


def load_data():
    with open(JSON_PATH) as f:
        return json.load(f)


def generate_html(runs):
    now = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M")

    # Build rows
    rows_html = ""
    for r in runs:
        rid = r["run_id"]
        sd = r["start_date"]
        dur = r["duration_years"]
        ann = r["annualized_return_pct"]
        ret = r["total_return_pct"]
        alpha = r.get("alpha_pct", 0)
        final = r["final_value"]
        trades = r["n_trades"]
        wr = r["win_rate"]
        pf = r["profit_factor"]
        dd = r["max_drawdown_pct"]

        # Top trades
        winners = r.get("top3_winners", [])
        losers = r.get("top3_losers", [])
        winners_html = "".join(
            f'<div class="trade win">${t["pnl"]:+,.0f} ({t["r"]:+.2f}%) — {t["t"]}<span class="reason">{t.get("reason","")[:25]}</span></div>'
            for t in winners
        ) or "<div class='trade'>None</div>"
        losers_html = "".join(
            f'<div class="trade loss">${t["pnl"]:+,.0f} ({t["r"]:+.2f}%) — {t["t"]}<span class="reason">{t.get("reason","")[:25]}</span></div>'
            for t in losers
        ) or "<div class='trade'>None</div>"

        # Exit reasons
        exits = r.get("exit_reasons", {})
        exits_html = "".join(
            f'<div class="exit-row"><span class="exit-name">{reason}</span>'
            f'<span class="exit-count">{data["count"]:,} trades</span>'
            f'<span class="exit-wr {"green" if data["wins"]/data["count"]*100 > 50 else "red"}">{data["wins"]/data["count"]*100:.0f}% WR</span>'
            f'<span class="exit-pnl {"green" if data["total_pnl"] > 0 else "red"}">${data["total_pnl"]:+,.0f}</span></div>'
            for reason, data in sorted(exits.items(), key=lambda x: -x[1]["count"])
        )

        ret_cls = "green" if ret > 0 else "red"
        ann_cls = "green" if ann > 0 else "red"
        dd_cls = "red"

        rows_html += f"""
        <tr class="run-row" onclick="toggleRun({rid})">
            <td>{rid}</td>
            <td>{sd}</td>
            <td>{dur}y</td>
            <td class="{ann_cls}">{ann:+.2f}%</td>
            <td class="{ret_cls}">{ret:+.0f}%</td>
            <td class="green">{alpha:+.0f}%</td>
            <td>${final:,.0f}</td>
            <td>{trades:,}</td>
            <td>{wr:.1f}%</td>
            <td>{pf:.2f}</td>
            <td class="{dd_cls}">{dd:.1f}%</td>
        </tr>
        <tr id="run-{rid}" class="run-detail" style="display:none;">
            <td colspan="11">
                <div class="detail-grid">
                    <div class="detail-card">
                        <div class="detail-title">🏆 Top Winners</div>
                        {winners_html}
                    </div>
                    <div class="detail-card">
                        <div class="detail-title">💀 Top Losers</div>
                        {losers_html}
                    </div>
                    <div class="detail-card detail-wide">
                        <div class="detail-title">📊 Exit Reasons</div>
                        {exits_html}
                    </div>
                </div>
            </td>
        </tr>
        """

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Golden Cross Rotation — Run Viewer</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0a0a0f; color: #e2e8f0; padding: 24px; }}
  h1 {{ font-size: 1.8rem; margin-bottom: 4px; background: linear-gradient(135deg, #22d3ee, #10b981); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
  .subtitle {{ color: #64748b; font-size: 0.9rem; margin-bottom: 20px; }}
  .controls {{ display: flex; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }}
  .controls input, .controls select {{ background: #1e293b; border: 1px solid #334155; color: #e2e8f0; padding: 8px 12px; border-radius: 6px; font-size: 0.85rem; }}
  .controls input {{ flex: 1; min-width: 200px; }}
  .controls select {{ cursor: pointer; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.82rem; }}
  th {{ text-align: left; padding: 10px 8px; color: #64748b; font-weight: 500; text-transform: uppercase; font-size: 0.7rem; letter-spacing: 0.5px; border-bottom: 2px solid #1e293b; cursor: pointer; user-select: none; }}
  th:hover {{ color: #22d3ee; }}
  td {{ padding: 8px; border-bottom: 1px solid #1e293b; }}
  tr.run-row:hover {{ background: #1a2332; cursor: pointer; }}
  .green {{ color: #10b981; }}
  .red {{ color: #ef4444; }}
  .run-detail td {{ padding: 16px 24px; background: #0f172a; border-bottom: 2px solid #22d3ee; }}
  .detail-grid {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; }}
  .detail-card {{ background: #1a2332; border-radius: 8px; padding: 12px; }}
  .detail-wide {{ grid-column: span 1; }}
  .detail-title {{ font-size: 0.85rem; font-weight: 600; color: #22d3ee; margin-bottom: 8px; }}
  .trade {{ padding: 4px 0; font-size: 0.8rem; border-bottom: 1px solid #1e293b; }}
  .trade.win {{ color: #10b981; }}
  .trade.loss {{ color: #ef4444; }}
  .trade .reason {{ color: #64748b; font-size: 0.7rem; margin-left: 8px; }}
  .exit-row {{ display: flex; gap: 12px; padding: 4px 0; font-size: 0.8rem; border-bottom: 1px solid #1e293b; }}
  .exit-name {{ flex: 1; color: #94a3b8; }}
  .exit-count {{ width: 100px; color: #64748b; }}
  .exit-wr {{ width: 70px; }}
  .exit-pnl {{ width: 120px; text-align: right; }}
  .summary {{ display: flex; gap: 24px; margin-bottom: 16px; flex-wrap: wrap; }}
  .summary-item {{ background: #0f172a; border: 1px solid #1e293b; border-radius: 8px; padding: 12px 20px; text-align: center; }}
  .summary-value {{ font-size: 1.3rem; font-weight: 700; }}
  .summary-label {{ font-size: 0.7rem; color: #64748b; text-transform: uppercase; }}
  @media (max-width: 900px) {{ .detail-grid {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>

<h1>Golden Cross Rotation — Run Viewer</h1>
<p class="subtitle">100 randomized backtests with crisis override | Click any row to expand trade details</p>

<div class="summary">
  <div class="summary-item">
    <div class="summary-value" style="color:#22d3ee;">{len(runs)}</div>
    <div class="summary-label">Total Runs</div>
  </div>
  <div class="summary-item">
    <div class="summary-value" style="color:#10b981;">{sum(r['annualized_return_pct'] for r in runs)/len(runs):+.1f}%</div>
    <div class="summary-label">Mean Ann Return</div>
  </div>
  <div class="summary-item">
    <div class="summary-value" style="color:#10b981;">{sum(r['total_return_pct'] for r in runs)/len(runs):+.0f}%</div>
    <div class="summary-label">Mean Total Return</div>
  </div>
  <div class="summary-item">
    <div class="summary-value" style="color:#f59e0b;">{sum(r['win_rate'] for r in runs)/len(runs):.1f}%</div>
    <div class="summary-label">Avg Win Rate</div>
  </div>
  <div class="summary-item">
    <div class="summary-value" style="color:#ef4444;">{sum(r['max_drawdown_pct'] for r in runs)/len(runs):.1f}%</div>
    <div class="summary-label">Avg Max DD</div>
  </div>
</div>

<div class="controls">
  <input type="text" id="search" placeholder="Search by start date or run ID..." onkeyup="filterRuns()">
  <select id="sort" onchange="sortRuns()">
    <option value="run_id">Sort by Run ID</option>
    <option value="annualized_return_pct">Sort by Annualized Return</option>
    <option value="total_return_pct">Sort by Total Return</option>
    <option value="max_drawdown_pct">Sort by Max Drawdown</option>
    <option value="win_rate">Sort by Win Rate</option>
    <option value="n_trades">Sort by Trade Count</option>
    <option value="start_date">Sort by Start Date</option>
  </select>
</div>

<table>
  <thead>
    <tr>
      <th onclick="sortTable(0)">#</th>
      <th onclick="sortTable(1)">Start</th>
      <th onclick="sortTable(2)">Dur</th>
      <th onclick="sortTable(3)">Ann Ret</th>
      <th onclick="sortTable(4)">Total Ret</th>
      <th onclick="sortTable(5)">Alpha</th>
      <th onclick="sortTable(6)">Final</th>
      <th onclick="sortTable(7)">Trades</th>
      <th onclick="sortTable(8)">Win%</th>
      <th onclick="sortTable(9)">PF</th>
      <th onclick="sortTable(10)">MaxDD</th>
    </tr>
  </thead>
  <tbody id="run-table">
    {rows_html}
  </tbody>
</table>

<script>
let sortAsc = {{}};
function toggleRun(id) {{
    const row = document.getElementById('run-' + id);
    row.style.display = row.style.display === 'none' ? 'table-row' : 'none';
}}

function filterRuns() {{
    const q = document.getElementById('search').value.toLowerCase();
    document.querySelectorAll('.run-row').forEach(r => {{
        r.style.display = r.innerText.toLowerCase().includes(q) ? '' : 'none';
    }});
}}

function sortRuns() {{
    const key = document.getElementById('sort').value;
    const tbody = document.getElementById('run-table');
    const rows = Array.from(tbody.querySelectorAll('.run-row'));
    const idx = {{'run_id':0,'start_date':1,'annualized_return_pct':3,'total_return_pct':4,'max_drawdown_pct':10,'win_rate':8,'n_trades':7}}[key] || 0;
    sortAsc[key] = !sortAsc[key];
    rows.sort((a, b) => {{
        let va = a.cells[idx]?.innerText.replace('%','').replace('$','').replace(',','') || '0';
        let vb = b.cells[idx]?.innerText.replace('%','').replace('$','').replace(',','') || '0';
        let na = parseFloat(va), nb = parseFloat(vb);
        if (!isNaN(na) && !isNaN(nb)) return sortAsc[key] ? na - nb : nb - na;
        return sortAsc[key] ? va.localeCompare(vb) : vb.localeCompare(va);
    }});
    rows.forEach((r, i) => tbody.appendChild(r));
}}

function sortTable(col) {{
    const tbody = document.getElementById('run-table');
    const rows = Array.from(tbody.querySelectorAll('.run-row'));
    sortAsc[col] = !sortAsc[col];
    rows.sort((a, b) => {{
        let va = a.cells[col]?.innerText.replace('%','').replace('$','').replace(',','') || '0';
        let vb = b.cells[col]?.innerText.replace('%','').replace('$','').replace(',','') || '0';
        let na = parseFloat(va), nb = parseFloat(vb);
        if (!isNaN(na) && !isNaN(nb)) return sortAsc[col] ? na - nb : nb - na;
        return sortAsc[col] ? va.localeCompare(vb) : vb.localeCompare(va);
    }});
    rows.forEach((r, i) => tbody.appendChild(r));
}}
</script>

<div style="text-align:center;color:#475569;font-size:0.75rem;margin-top:24px;padding:16px;border-top:1px solid #1e293b;">
  Generated {now} | Golden Cross Rotation Strategy — 100-Run Validation
</div>

</body>
</html>"""
    return html


def main():
    print("📥 Loading validation data...")
    runs = load_data()
    print(f"  Loaded {len(runs)} runs")

    print("📝 Generating run viewer...")
    html = generate_html(runs)
    with open(OUTPUT_PATH, "w") as f:
        f.write(html)
    print(f"  ✅ Saved to: {OUTPUT_PATH}")
    print(f"  File size: {OUTPUT_PATH.stat().st_size / 1024:.0f} KB")
    print("  Open in browser to explore all 100 runs with trade details.")


if __name__ == "__main__":
    main()
