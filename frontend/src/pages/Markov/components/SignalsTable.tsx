import { useState } from "react";

interface Signal {
  ticker: string;
  sector: string;
  signal: string;
  conviction: number;
  price: number;
  regime: string;
  vol_regime: string;
  etf: string;
}

interface SignalsTableProps {
  signals: Signal[];
  totalScanned: number;
  loading: boolean;
  isDarkMode: boolean;
}

export default function SignalsTable({ signals, totalScanned, loading, isDarkMode }: SignalsTableProps) {
  const [showAll, setShowAll] = useState(false);
  // Use a reasonable default for the actionable filter threshold
  const actionableThreshold = 0.6;
  const actionable = signals.filter((s) => s.signal === "BUY" && s.conviction >= actionableThreshold);
  const display = showAll ? signals : actionable;

  const muted = isDarkMode ? "rgba(255,255,255,0.7)" : "#6e6e73";
  const border = isDarkMode ? "rgba(255,255,255,0.12)" : "#d2d2d7";
  const rowBorder = isDarkMode ? "rgba(255,255,255,0.06)" : "#f0f0f0";
  const barBg = isDarkMode ? "rgba(255,255,255,0.15)" : "#e5e7eb";

  if (loading) {
    return <div style={{ padding: 24, textAlign: "center", color: muted }}>Loading signals...</div>;
  }

  if (signals.length === 0) {
    return <div style={{ padding: 24, textAlign: "center", color: muted }}>No signals found. Run a scan to begin.</div>;
  }

  return (
    <div style={{ padding: "24px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <h2 style={{ fontSize: 20, fontWeight: 600 }}>
          Signals ({display.length} of {signals.length})
        </h2>
        <div style={{ fontSize: 12, color: muted }}>Scanned: {totalScanned} tickers</div>
      </div>

      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <button
          onClick={() => setShowAll(false)}
          style={{
            padding: "6px 16px",
            borderRadius: 6,
            border: `1px solid ${!showAll ? "#10B981" : border}`,
            background: !showAll ? "rgba(16, 185, 129, 0.1)" : "transparent",
            cursor: "pointer",
            fontSize: 13,
            color: "inherit",
          }}
        >
          Actionable
        </button>
        <button
          onClick={() => setShowAll(true)}
          style={{
            padding: "6px 16px",
            borderRadius: 6,
            border: `1px solid ${showAll ? "#10B981" : border}`,
            background: showAll ? "rgba(16, 185, 129, 0.1)" : "transparent",
            cursor: "pointer",
            fontSize: 13,
            color: "inherit",
          }}
        >
          Full List
        </button>
      </div>

      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
          <thead>
            <tr style={{ borderBottom: `1px solid ${border}` }}>
              <th style={{ textAlign: "left", padding: "8px 12px", fontWeight: 600 }}>Rank</th>
              <th style={{ textAlign: "left", padding: "8px 12px", fontWeight: 600 }}>Ticker</th>
              <th style={{ textAlign: "left", padding: "8px 12px", fontWeight: 600 }}>Sector</th>
              <th style={{ textAlign: "left", padding: "8px 12px", fontWeight: 600 }}>Signal</th>
              <th style={{ textAlign: "right", padding: "8px 12px", fontWeight: 600 }}>Conviction</th>
              <th style={{ textAlign: "right", padding: "8px 12px", fontWeight: 600 }}>Price</th>
              <th style={{ textAlign: "left", padding: "8px 12px", fontWeight: 600 }}>ETF</th>
            </tr>
          </thead>
          <tbody>
            {display.map((s, i) => (
              <tr key={`${s.ticker}-${i}`} style={{ borderBottom: `1px solid ${rowBorder}` }}>
                <td style={{ padding: "8px 12px" }}>{i + 1}</td>
                <td style={{ padding: "8px 12px", fontWeight: 600 }}>{s.ticker}</td>
                <td style={{ padding: "8px 12px" }}>{s.sector}</td>
                <td style={{ padding: "8px 12px" }}>
                  <span style={{
                    color: s.signal === "BUY" ? "#10B981" : s.signal === "SELL" ? "#EF4444" : muted,
                    fontWeight: 600,
                  }}>
                    {s.signal === "BUY" ? "▲ BUY" : s.signal === "SELL" ? "▼ SELL" : "● HOLD"}
                  </span>
                </td>
                <td style={{ padding: "8px 12px", textAlign: "right" }}>
                  <div style={{
                    display: "inline-block",
                    width: 60,
                    height: 6,
                    borderRadius: 3,
                    background: barBg,
                    marginRight: 8,
                    verticalAlign: "middle",
                  }}>
                    <div style={{
                      width: `${(s.conviction * 100).toFixed(0)}%`,
                      height: "100%",
                      borderRadius: 3,
                      background: s.conviction >= 0.6 ? "#10B981" : "#F59E0B",
                    }} />
                  </div>
                  {(s.conviction * 100).toFixed(0)}%
                </td>
                <td style={{ padding: "8px 12px", textAlign: "right" }}>${s.price.toFixed(2)}</td>
                <td style={{ padding: "8px 12px" }}>{s.etf}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}