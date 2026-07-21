"""Capture baseline KPIs from the original daily_golden_cross_rotation.py.

Runs the original main() but with a 2-year window (fast) and dumps the
summary KPIs to baseline_kpis.json. Run this once; the JSON is the
ground truth for the parity test.
"""
import json
import os
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
os.environ.setdefault("DB_USER", "postgres")
os.environ.setdefault("DB_PASSWORD", "sarina00")
os.environ.setdefault("DB_HOST", "127.0.0.1")
os.environ.setdefault("DB_PORT", "5431")
os.environ.setdefault("DB_NAME", "sp1500_1d")

# Import original module
import importlib.util
spec = importlib.util.spec_from_file_location(
    "orig_dgcr",
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "strategies", "daily_golden_cross_rotation.py"),
)
orig = importlib.util.module_from_spec(spec)
spec.loader.exec_module(orig)

# Monkeypatch the constants to a 2-year window for fast baseline capture
orig.AS_OF = "2022-01-01"
orig.END = "2024-01-01"
orig.CAPITAL = 100_000.0

# Run the original main() — it writes to docs/reports/summary.json
orig.main()

# Read the summary it just wrote
report_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "docs", "reports")
with open(os.path.join(report_dir, "summary.json")) as f:
    summary = json.load(f)
with open(os.path.join(report_dir, "trades.json")) as f:
    trades = json.load(f)

# Build baseline
baseline = {
    "window": {"as_of": orig.AS_OF, "end": orig.END},
    "kpis": {
        "total_return_pct": summary["total_return_pct"],
        "cagr_pct": summary["cagr_pct"],
        "n_trades": summary["total_trades"],
        "win_rate": summary["win_rate"],
        "profit_factor": summary["profit_factor"],
        "spy_return_pct": summary.get("spy_return_pct", 0),
    },
    "exit_reason_counts": summary["exit_reasons"],
    "first_5_trade_signatures": [
        {
            "ticker": t["ticker"],
            "entry_date": t["entry_date"],
            "exit_date": t.get("exit_date", ""),
            "return_pct": t["return_pct"],
        }
        for t in trades if t["side"] == "SELL"
    ][:5],
}

# Save baseline
out_path = os.path.join(os.path.dirname(__file__), "baseline_kpis.json")
with open(out_path, "w") as f:
    json.dump(baseline, f, indent=2)
print(f"Baseline written to {out_path}")
print(json.dumps(baseline["kpis"], indent=2))
