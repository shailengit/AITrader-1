"""Generate interactive HTML run-viewer reports for batch backtest experiments.

Each report is a self-contained HTML file with:
  - Summary stats (mean return, win rate, profit factor, etc.)
  - Sortable/filterable table of all runs
  - Expandable detail rows per run (top winners, top losers, exit reasons)
  - Strategy code and parameters that produced the results

Reports are saved to docs/reports/ with a timestamped filename.
"""

import os
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Where reports are stored
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
REPORTS_DIR = REPO_ROOT / "docs" / "reports"


def _json_safe(val: Any) -> Any:
    """Convert numpy types to native Python for JSON serialization."""
    if hasattr(val, "item"):
        return val.item()
    return val


def _compute_stats(experiments: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute aggregate stats across all completed experiments."""
    completed = [e for e in experiments if e.get("status") == "completed" and e.get("kpis")]
    if not completed:
        return {
            "n_total": len(experiments),
            "n_completed": 0,
            "n_failed": sum(1 for e in experiments if e.get("status") == "failed"),
            "mean_return": 0,
            "mean_alpha": 0,
            "mean_win_rate": 0,
            "mean_profit_factor": 0,
            "mean_sharpe": 0,
            "mean_trades": 0,
        }

    returns = []
    alphas = []
    win_rates = []
    profit_factors = []
    sharpes = []
    trades = []

    for e in completed:
        k = e.get("kpis", {})
        returns.append(k.get("total_return_pct", 0) or 0)
        alphas.append(k.get("alpha_pct", 0) or 0)
        win_rates.append(k.get("win_rate", 0) or 0)
        profit_factors.append(k.get("profit_factor", 0) or 0)
        sharpes.append(k.get("sharpe_ratio", 0) or 0)
        trades.append(k.get("total_trades", 0) or 0)

    n_failed = sum(1 for e in experiments if e.get("status") == "failed")

    return {
        "n_total": len(experiments),
        "n_completed": len(completed),
        "n_failed": n_failed,
        "mean_return": sum(returns) / len(returns) if returns else 0,
        "mean_alpha": sum(alphas) / len(alphas) if alphas else 0,
        "mean_win_rate": sum(win_rates) / len(win_rates) if win_rates else 0,
        "mean_profit_factor": sum(profit_factors) / len(profit_factors) if profit_factors else 0,
        "mean_sharpe": sum(sharpes) / len(sharpes) if sharpes else 0,
        "mean_trades": sum(trades) / len(trades) if trades else 0,
        "best_return": max(returns) if returns else 0,
        "worst_return": min(returns) if returns else 0,
    }


def _format_pct(val: float) -> str:
    """Format a percentage value with sign."""
    return f"{val:+.2f}%"


def _format_dollar(val: float) -> str:
    """Format a dollar value."""
    return f"${val:,.2f}"


def _color_class(val: float) -> str:
    """Return CSS class for positive/negative values."""
    return "green" if val >= 0 else "red"


def _escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;"))


def _build_run_rows(experiments: List[Dict[str, Any]]) -> str:
    """Build the HTML table rows for all runs."""
    rows_html = ""

    for idx, exp in enumerate(experiments, 1):
        status = exp.get("status", "unknown")
        k = exp.get("kpis") or {}
        start = exp.get("start_date", "")
        end = exp.get("end_date", "")
        run_idx = exp.get("run_index", idx)

        # Compute duration
        dur = ""
        if start and end:
            try:
                sd = datetime.strptime(str(start)[:10], "%Y-%m-%d")
                ed = datetime.strptime(str(end)[:10], "%Y-%m-%d")
                days = (ed - sd).days
                if days >= 365:
                    dur = f"{days / 365.25:.1f}y"
                elif days >= 30:
                    dur = f"{days / 30.44:.1f}m"
                else:
                    dur = f"{days}d"
            except (ValueError, TypeError):
                dur = ""

        if status == "completed":
            total_ret = k.get("total_return_pct", 0) or 0
            ann_ret = k.get("cagr_pct", 0) or 0
            alpha = k.get("alpha_pct", 0) or 0
            final_val = k.get("final_portfolio", 0) or 0
            n_trades = k.get("total_trades", 0) or 0
            win_rate = k.get("win_rate", 0) or 0
            pf = k.get("profit_factor", 0) or 0
            sharpe = k.get("sharpe_ratio", 0) or 0

            row_class = ""
            ret_str = f'<span class="{_color_class(total_ret)}">{_format_pct(total_ret)}</span>'
            ann_str = f'<span class="{_color_class(ann_ret)}">{_format_pct(ann_ret)}</span>'
            alpha_str = f'<span class="{_color_class(alpha)}">{_format_pct(alpha)}</span>'
            final_str = _format_dollar(final_val)
            trades_str = str(n_trades)
            wr_str = f'{win_rate:.1f}%'
            pf_str = f'{pf:.2f}'
            sharpe_str = f'{sharpe:.2f}'
        elif status == "failed":
            row_class = "opacity-50"
            ret_str = ann_str = alpha_str = "—"
            final_str = "—"
            trades_str = "—"
            wr_str = "—"
            pf_str = "—"
            sharpe_str = "—"
        else:
            row_class = "opacity-50"
            ret_str = ann_str = alpha_str = "…"
            final_str = "…"
            trades_str = "…"
            wr_str = "…"
            pf_str = "…"
            sharpe_str = "…"

        # Build detail row content
        detail_html = _build_detail_row(exp)

        rows_html += f"""
        <tr class="run-row {row_class}" onclick="toggleRun({idx})">
            <td>{run_idx}</td>
            <td>{start}</td>
            <td>{dur}</td>
            <td>{ann_str}</td>
            <td>{ret_str}</td>
            <td>{alpha_str}</td>
            <td>{final_str}</td>
            <td>{trades_str}</td>
            <td>{wr_str}</td>
            <td>{pf_str}</td>
            <td>{sharpe_str}</td>
        </tr>
        <tr id="run-{idx}" class="run-detail" style="display:none;">
            <td colspan="11">
                {detail_html}
            </td>
        </tr>"""

    return rows_html


def _build_detail_row(exp: Dict[str, Any]) -> str:
    """Build the expandable detail section for a single run."""
    k = exp.get("kpis") or {}
    status = exp.get("status", "unknown")

    if status != "completed" or not k:
        error_msg = exp.get("error_message", "Unknown error")
        return f"""
        <div class="detail-card">
            <div class="detail-title">❌ Failed</div>
            <div style="color:#ef4444;">{_escape_html(error_msg)}</div>
        </div>"""

    # Exit reasons breakdown
    exit_reasons = k.get("exit_reasons", {})
    exit_html = ""
    if exit_reasons:
        for reason, count in sorted(exit_reasons.items(), key=lambda x: -x[1]):
            exit_html += f"""
            <div class="exit-row">
                <span class="exit-name">{_escape_html(reason)}</span>
                <span class="exit-count">{count} trades</span>
            </div>"""
    else:
        exit_html = '<div class="exit-row"><span class="exit-name">No exits</span></div>'

    # Top/bottom trades from KPIs (if available)
    top_winners = k.get("top_winners", [])
    top_losers = k.get("top_losers", [])

    winners_html = ""
    if top_winners:
        for t in top_winners[:3]:
            ticker = t.get("ticker", "")
            ret = t.get("return_pct", 0)
            pnl = t.get("pnl_dollars", 0)
            reason = t.get("exit_reason", "")
            winners_html += f'<div class="trade win">${pnl:+,.2f} ({ret:+.2f}%) — {ticker}<span class="reason">{_escape_html(reason)}</span></div>'
    else:
        winners_html = '<div class="trade win">No trade data</div>'

    losers_html = ""
    if top_losers:
        for t in top_losers[:3]:
            ticker = t.get("ticker", "")
            ret = t.get("return_pct", 0)
            pnl = t.get("pnl_dollars", 0)
            reason = t.get("exit_reason", "")
            losers_html += f'<div class="trade loss">${pnl:+,.2f} ({ret:+.2f}%) — {ticker}<span class="reason">{_escape_html(reason)}</span></div>'
    else:
        losers_html = '<div class="trade loss">No trade data</div>'

    # Key metrics
    total_ret = k.get("total_return_pct", 0) or 0
    ann_ret = k.get("cagr_pct", 0) or 0
    alpha = k.get("alpha_pct", 0) or 0
    sharpe = k.get("sharpe_ratio", 0) or 0
    win_rate = k.get("win_rate", 0) or 0
    pf = k.get("profit_factor", 0) or 0
    n_trades = k.get("total_trades", 0) or 0
    spy_ret = k.get("spy_return_pct", 0) or 0
    final_val = k.get("final_portfolio", 0) or 0
    avg_win = k.get("avg_winner", 0) or 0
    avg_loss = k.get("avg_loser", 0) or 0

    return f"""
        <div class="detail-grid">
            <div class="detail-card">
                <div class="detail-title">📊 Key Metrics</div>
                <div class="exit-row"><span class="exit-name">Total Return</span><span class="exit-pnl" style="color:{'#10b981' if total_ret >= 0 else '#ef4444'}">{_format_pct(total_ret)}</span></div>
                <div class="exit-row"><span class="exit-name">Annualized (CAGR)</span><span class="exit-pnl" style="color:{'#10b981' if ann_ret >= 0 else '#ef4444'}">{_format_pct(ann_ret)}</span></div>
                <div class="exit-row"><span class="exit-name">Alpha vs SPY</span><span class="exit-pnl" style="color:{'#10b981' if alpha >= 0 else '#ef4444'}">{_format_pct(alpha)}</span></div>
                <div class="exit-row"><span class="exit-name">Sharpe Ratio</span><span class="exit-pnl">{sharpe:.2f}</span></div>
                <div class="exit-row"><span class="exit-name">SPY Return</span><span class="exit-pnl">{_format_pct(spy_ret)}</span></div>
                <div class="exit-row"><span class="exit-name">Final Portfolio</span><span class="exit-pnl">{_format_dollar(final_val)}</span></div>
            </div>
            <div class="detail-card">
                <div class="detail-title">📈 Trade Stats</div>
                <div class="exit-row"><span class="exit-name">Total Trades</span><span class="exit-pnl">{n_trades}</span></div>
                <div class="exit-row"><span class="exit-name">Win Rate</span><span class="exit-pnl">{win_rate:.1f}%</span></div>
                <div class="exit-row"><span class="exit-name">Profit Factor</span><span class="exit-pnl">{pf:.2f}</span></div>
                <div class="exit-row"><span class="exit-name">Avg Winner</span><span class="exit-pnl" style="color:#10b981">{_format_dollar(avg_win)}</span></div>
                <div class="exit-row"><span class="exit-name">Avg Loser</span><span class="exit-pnl" style="color:#ef4444">{_format_dollar(avg_loss)}</span></div>
            </div>
            <div class="detail-card">
                <div class="detail-title">🏆 Top Winners</div>
                {winners_html}
            </div>
            <div class="detail-card">
                <div class="detail-title">💀 Top Losers</div>
                {losers_html}
            </div>
            <div class="detail-card detail-wide">
                <div class="detail-title">📋 Exit Reasons</div>
                {exit_html}
            </div>
        </div>"""


def generate_run_viewer(
    experiments: List[Dict[str, Any]],
    strategy_name: str = "Unnamed Strategy",
    strategy_code: str = "",
    strategy_params: Optional[Dict[str, Any]] = None,
    batch_id: str = "",
    session_id: str = "",
) -> str:
    """Generate a self-contained HTML run-viewer report.

    Args:
        experiments: List of experiment dicts with status, kpis, start_date, end_date, etc.
        strategy_name: Human-readable strategy name.
        strategy_code: The full Python source code of the strategy.
        strategy_params: Dict of strategy parameters (AS_OF, END, MAX_HOLDINGS, etc.).
        batch_id: UUID of the batch.
        session_id: UUID of the session.

    Returns:
        Absolute path to the generated HTML file.
    """
    os.makedirs(REPORTS_DIR, exist_ok=True)

    stats = _compute_stats(experiments)
    run_rows = _build_run_rows(experiments)

    # Format strategy params for display
    params_html = ""
    if strategy_params:
        params_html = '<div class="detail-title">⚙️ Parameters</div><div class="params-grid">'
        for key, val in sorted(strategy_params.items()):
            params_html += f'<div class="param-item"><span class="param-key">{_escape_html(key)}</span><span class="param-val">{_escape_html(str(val))}</span></div>'
        params_html += "</div>"

    # Format strategy code (truncated for display, full in a collapsible section)
    code_preview = ""
    if strategy_code:
        code_lines = strategy_code.split("\n")
        # Show first 30 lines as preview
        preview_lines = code_lines[:30]
        code_preview = _escape_html("\n".join(preview_lines))
        if len(code_lines) > 30:
            code_preview += "\n..."

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = "".join(c if c.isalnum() or c in " -_" else "_" for c in strategy_name)[:40]
    filename = f"batch_{safe_name}_{timestamp}.html"
    filepath = os.path.join(REPORTS_DIR, filename)

    # Color for mean return
    mean_ret_color = "#10b981" if stats["mean_return"] >= 0 else "#ef4444"
    mean_alpha_color = "#10b981" if stats["mean_alpha"] >= 0 else "#ef4444"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_escape_html(strategy_name)} — Run Viewer</title>
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
  .opacity-50 {{ opacity: 0.5; }}
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
  .exit-pnl {{ width: 120px; text-align: right; }}
  .summary {{ display: flex; gap: 24px; margin-bottom: 16px; flex-wrap: wrap; }}
  .summary-item {{ background: #0f172a; border: 1px solid #1e293b; border-radius: 8px; padding: 12px 20px; text-align: center; }}
  .summary-value {{ font-size: 1.3rem; font-weight: 700; }}
  .summary-label {{ font-size: 0.7rem; color: #64748b; text-transform: uppercase; }}
  .strategy-section {{ background: #0f172a; border: 1px solid #1e293b; border-radius: 8px; padding: 16px; margin-bottom: 16px; }}
  .strategy-section h3 {{ color: #22d3ee; font-size: 1rem; margin-bottom: 8px; }}
  .params-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 8px; }}
  .param-item {{ display: flex; justify-content: space-between; padding: 4px 8px; background: #1a2332; border-radius: 4px; font-size: 0.8rem; }}
  .param-key {{ color: #64748b; }}
  .param-val {{ color: #e2e8f0; font-family: 'JetBrains Mono', monospace; }}
  pre.code-block {{ background: #1a2332; border: 1px solid #334155; border-radius: 6px; padding: 12px; font-size: 0.75rem; line-height: 1.4; overflow-x: auto; max-height: 300px; color: #e2e8f0; }}
  .toggle-code {{ color: #22d3ee; cursor: pointer; font-size: 0.8rem; margin-top: 4px; display: inline-block; }}
  @media (max-width: 900px) {{ .detail-grid {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>

<h1>{_escape_html(strategy_name)} — Run Viewer</h1>
<p class="subtitle">{stats["n_completed"]} completed runs | Batch: {batch_id[:8] if batch_id else "N/A"} | Generated {datetime.now().strftime("%Y-%m-%d %H:%M")}</p>

<div class="summary">
  <div class="summary-item">
    <div class="summary-value" style="color:#22d3ee;">{stats["n_total"]}</div>
    <div class="summary-label">Total Runs</div>
  </div>
  <div class="summary-item">
    <div class="summary-value" style="color:{mean_ret_color};">{_format_pct(stats["mean_return"])}</div>
    <div class="summary-label">Mean Return</div>
  </div>
  <div class="summary-item">
    <div class="summary-value" style="color:{mean_alpha_color};">{_format_pct(stats["mean_alpha"])}</div>
    <div class="summary-label">Mean Alpha</div>
  </div>
  <div class="summary-item">
    <div class="summary-value" style="color:#f59e0b;">{stats["mean_win_rate"]:.1f}%</div>
    <div class="summary-label">Avg Win Rate</div>
  </div>
  <div class="summary-item">
    <div class="summary-value" style="color:#22d3ee;">{stats["mean_profit_factor"]:.2f}</div>
    <div class="summary-label">Avg Profit Factor</div>
  </div>
  <div class="summary-item">
    <div class="summary-value" style="color:#22d3ee;">{stats["mean_sharpe"]:.2f}</div>
    <div class="summary-label">Avg Sharpe</div>
  </div>
  <div class="summary-item">
    <div class="summary-value" style="color:#64748b;">{stats["mean_trades"]:.0f}</div>
    <div class="summary-label">Avg Trades</div>
  </div>
</div>

<div class="strategy-section">
    <h3>📋 Strategy Details</h3>
    {params_html}
    <div style="margin-top:8px;">
        <span class="toggle-code" onclick="toggleCode()">▶ Show strategy code</span>
        <pre id="strategy-code" class="code-block" style="display:none;">{code_preview}</pre>
    </div>
</div>

<div class="controls">
  <input type="text" id="search" placeholder="Search by start date or run ID..." onkeyup="filterRuns()">
  <select id="sort" onchange="sortRuns()">
    <option value="run_index">Sort by Run #</option>
    <option value="total_return_pct">Sort by Total Return</option>
    <option value="cagr_pct">Sort by Annualized Return</option>
    <option value="alpha_pct">Sort by Alpha</option>
    <option value="win_rate">Sort by Win Rate</option>
    <option value="profit_factor">Sort by Profit Factor</option>
    <option value="sharpe_ratio">Sort by Sharpe</option>
    <option value="total_trades">Sort by Trade Count</option>
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
      <th onclick="sortTable(10)">Sharpe</th>
    </tr>
  </thead>
  <tbody id="run-table">
    {run_rows}
  </tbody>
</table>

<script>
let currentSort = {{ col: 0, asc: true }};

function toggleRun(id) {{
    const row = document.getElementById('run-' + id);
    if (row) row.style.display = row.style.display === 'none' ? 'table-row' : 'none';
}}

function toggleCode() {{
    const el = document.getElementById('strategy-code');
    const toggle = event.target;
    if (el.style.display === 'none') {{
        el.style.display = 'block';
        toggle.textContent = '▼ Hide strategy code';
    }} else {{
        el.style.display = 'none';
        toggle.textContent = '▶ Show strategy code';
    }}
}}

function filterRuns() {{
    const q = document.getElementById('search').value.toLowerCase();
    const rows = document.querySelectorAll('.run-row');
    rows.forEach(row => {{
        const text = row.textContent.toLowerCase();
        row.style.display = text.includes(q) ? '' : 'none';
    }});
}}

function sortTable(col) {{
    const tbody = document.getElementById('run-table');
    const rows = Array.from(tbody.querySelectorAll('.run-row'));
    const asc = currentSort.col === col ? !currentSort.asc : true;
    currentSort = {{ col, asc }};

    rows.sort((a, b) => {{
        const aVal = a.cells[col].textContent.trim();
        const bVal = b.cells[col].textContent.trim();
        const aNum = parseFloat(aVal.replace(/[$%,]/g, '')) || 0;
        const bNum = parseFloat(bVal.replace(/[$%,]/g, '')) || 0;
        if (aVal === '—' || aVal === '…') return 1;
        if (bVal === '—' || bVal === '…') return -1;
        return asc ? aNum - bNum : bNum - aNum;
    }});

    rows.forEach(row => {{
        const idx = row.cells[0].textContent.trim();
        const detail = document.getElementById('run-' + idx);
        tbody.appendChild(row);
        if (detail) tbody.appendChild(detail);
    }});
}}

function sortRuns() {{
    const sortKey = document.getElementById('sort').value;
    const colMap = {{
        'run_index': 0, 'start_date': 1, 'total_return_pct': 4,
        'cagr_pct': 3, 'alpha_pct': 5, 'win_rate': 8,
        'profit_factor': 9, 'sharpe_ratio': 10, 'total_trades': 7
    }};
    sortTable(colMap[sortKey] || 0);
}}
</script>

</body>
</html>"""

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)

    logger.info("Run viewer report generated: %s", filepath)
    return filepath
