import { useState } from "react";

export interface ScanParams {
  model: "xgboost" | "lstm";
  threshold: number;
  minConviction: number;
  maxResults: number;
  asOfDate: string;  // YYYY-MM-DD, empty string = today
}

interface ControlPanelProps {
  onScan: (params: ScanParams) => void;
  loading: boolean;
}

export default function ControlPanel({ onScan, loading }: ControlPanelProps) {
  const [model, setModel] = useState<"xgboost" | "lstm">("xgboost");
  const [threshold, setThreshold] = useState(2.0);
  const [minConviction, setMinConviction] = useState(0.6);
  const [maxResults, setMaxResults] = useState(50);
  const [asOfDate, setAsOfDate] = useState("");

  return (
    <div style={{ maxWidth: 480, padding: "24px" }}>
      <h2 style={{ fontSize: 20, fontWeight: 600, marginBottom: 24 }}>
        Scan Controls
      </h2>

      {/* Model Toggle */}
      <div style={{ marginBottom: 20 }}>
        <label style={{ fontSize: 14, fontWeight: 500, display: "block", marginBottom: 8 }}>
          Model
        </label>
        <div style={{ display: "flex", gap: 12 }}>
          <button
            onClick={() => setModel("xgboost")}
            style={{
              padding: "8px 20px",
              borderRadius: 8,
              border: `2px solid ${model === "xgboost" ? "#10B981" : "#d2d2d7"}`,
              background: model === "xgboost" ? "rgba(16, 185, 129, 0.1)" : "transparent",
              cursor: "pointer",
              fontWeight: 500,
            }}
          >
            XGBoost (Fast)
          </button>
          <button
            onClick={() => setModel("lstm")}
            style={{
              padding: "8px 20px",
              borderRadius: 8,
              border: `2px solid ${model === "lstm" ? "#10B981" : "#d2d2d7"}`,
              background: model === "lstm" ? "rgba(16, 185, 129, 0.1)" : "transparent",
              cursor: "pointer",
              fontWeight: 500,
            }}
          >
            LSTM (Deep)
          </button>
        </div>
      </div>

      {/* Threshold Slider */}
      <div style={{ marginBottom: 20 }}>
        <label style={{ fontSize: 14, fontWeight: 500, display: "block", marginBottom: 8 }}>
          BUY/SELL Threshold: {threshold.toFixed(1)}%
        </label>
        <input
          type="range"
          min={0.5}
          max={5.0}
          step={0.5}
          value={threshold}
          onChange={(e) => setThreshold(parseFloat(e.target.value))}
          style={{ width: "100%" }}
        />
        <div style={{ fontSize: 11, opacity: 0.6, marginTop: 4 }}>
          Affects LSTM (trained on-the-fly). For XGBoost, use Retrain to apply a new threshold.
        </div>
      </div>

      {/* Min Conviction Slider */}
      <div style={{ marginBottom: 20 }}>
        <label style={{ fontSize: 14, fontWeight: 500, display: "block", marginBottom: 8 }}>
          Min Conviction: {minConviction.toFixed(2)}
        </label>
        <input
          type="range"
          min={0.3}
          max={0.95}
          step={0.05}
          value={minConviction}
          onChange={(e) => setMinConviction(parseFloat(e.target.value))}
          style={{ width: "100%" }}
        />
        <div style={{ fontSize: 11, opacity: 0.6, marginTop: 4 }}>
          Minimum confidence for a BUY signal. Also used by the Actionable filter.
        </div>
      </div>

      {/* Max Results */}
      <div style={{ marginBottom: 24 }}>
        <label style={{ fontSize: 14, fontWeight: 500, display: "block", marginBottom: 8 }}>
          Max Tickers to Scan
        </label>
        <input
          type="number"
          value={maxResults}
          onChange={(e) => setMaxResults(parseInt(e.target.value) || 50)}
          min={5}
          max={500}
          style={{
            padding: "8px 12px",
            borderRadius: 8,
            border: "1px solid #d2d2d7",
            width: 100,
          }}
        />
        <div style={{ fontSize: 11, opacity: 0.6, marginTop: 4 }}>
          Number of tickers to scan (5–500). Results are capped at this value.
        </div>
      </div>

      {/* As of Date */}
      <div style={{ marginBottom: 24 }}>
        <label style={{ fontSize: 14, fontWeight: 500, display: "block", marginBottom: 8 }}>
          As of Date
        </label>
        <input
          type="date"
          value={asOfDate}
          onChange={(e) => setAsOfDate(e.target.value)}
          style={{
            padding: "8px 12px",
            borderRadius: 8,
            border: "1px solid #d2d2d7",
            width: 180,
          }}
        />
        <div style={{ fontSize: 11, opacity: 0.6, marginTop: 4 }}>
          Scan as of this date (leave empty for today). Affects regime model, features, and labels.
        </div>
      </div>

      {/* Scan Button */}
      <button
        onClick={() => onScan({ model, threshold: threshold / 100, minConviction, maxResults, asOfDate })}
        disabled={loading}
        style={{
          padding: "12px 32px",
          borderRadius: 8,
          border: "none",
          background: loading ? "#9CA3AF" : "#10B981",
          color: "white",
          fontWeight: 600,
          cursor: loading ? "not-allowed" : "pointer",
          fontSize: 16,
        }}
      >
        {loading ? "Scanning..." : "Run Scan"}
      </button>
    </div>
  );
}