import { useState } from "react";

interface MetricCard {
  label: string;
  value: number | null;
  yoy: number | null;
  qoq: number | null;
  formatted: string;
}

interface FundamentalsData {
  ticker: string;
  metadata: {
    name?: string;
    sector?: string;
    industry?: string;
    market_cap?: number;
    beta?: number;
  };
  latest_price?: number | null;
  latest_quarter?: string | null;
  tabs: {
    income_statement: MetricCard[];
    balance_sheet: MetricCard[];
    cash_flow: MetricCard[];
    margins_ratios: MetricCard[];
  };
}

interface FundamentalsPanelProps {
  data: FundamentalsData | null;
  isLoading?: boolean;
  isDarkMode?: boolean;
}

const TAB_LABELS: Record<string, string> = {
  income_statement: "Income Statement",
  balance_sheet: "Balance Sheet",
  cash_flow: "Cash Flow",
  margins_ratios: "Margins & Ratios",
};

const TAB_ORDER = ["income_statement", "balance_sheet", "cash_flow", "margins_ratios"];

function GrowthBadge({ value, isDarkMode }: { value: number | null; isDarkMode: boolean }) {
  if (value == null) {
    return (
      <span
        style={{
          fontSize: "11px",
          fontWeight: 600,
          color: "var(--subtle)",
          backgroundColor: isDarkMode ? "rgba(255,255,255,0.04)" : "#f1f5f9",
          padding: "2px 8px",
          borderRadius: "999px",
        }}
      >
        N/A
      </span>
    );
  }

  const isPositive = value > 0;
  const color = isPositive ? "#10B981" : "#f43f5e";
  const bg = isPositive
    ? isDarkMode
      ? "rgba(16,185,129,0.1)"
      : "rgba(16,185,129,0.08)"
    : isDarkMode
      ? "rgba(244,63,94,0.1)"
      : "rgba(244,63,94,0.08)";

  return (
    <span
      style={{
        fontSize: "11px",
        fontWeight: 600,
        color,
        backgroundColor: bg,
        padding: "2px 8px",
        borderRadius: "999px",
      }}
    >
      {isPositive ? "+" : ""}
      {value.toFixed(1)}%
    </span>
  );
}

export default function FundamentalsPanel({ data, isLoading, isDarkMode = true }: FundamentalsPanelProps) {
  const [activeTab, setActiveTab] = useState("income_statement");

  if (isLoading) {
    return (
      <div
        style={{
          padding: "20px",
          borderRadius: "14px",
          backgroundColor: "var(--surface)",
          border: "1px solid var(--border)",
          marginBottom: "24px",
        }}
      >
        <div style={{ display: "flex", gap: "4px", marginBottom: "16px" }}>
          {TAB_ORDER.map((tab) => (
            <div
              key={tab}
              style={{
                padding: "6px 14px",
                borderRadius: "6px",
                fontSize: "13px",
                fontWeight: 600,
                backgroundColor: tab === activeTab ? "var(--accent)" : "transparent",
                color: tab === activeTab ? "#000000" : "var(--muted)",
              }}
            >
              {TAB_LABELS[tab]}
            </div>
          ))}
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "12px" }}>
          {Array.from({ length: 8 }).map((_, i) => (
            <div
              key={i}
              style={{
                padding: "14px",
                borderRadius: "10px",
                backgroundColor: isDarkMode ? "rgba(255,255,255,0.03)" : "#f8fafc",
                border: "1px solid var(--border)",
                height: "80px",
              }}
            />
          ))}
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div
        style={{
          padding: "20px",
          borderRadius: "14px",
          backgroundColor: "var(--surface)",
          border: "1px solid var(--border)",
          marginBottom: "24px",
          textAlign: "center",
          color: "var(--muted)",
          fontSize: "14px",
        }}
      >
        No fundamentals data available.
      </div>
    );
  }

  const currentMetrics = data.tabs[activeTab as keyof typeof data.tabs] || [];

  return (
    <div
      style={{
        padding: "20px",
        borderRadius: "14px",
        backgroundColor: "var(--surface)",
        border: "1px solid var(--border)",
        marginBottom: "24px",
      }}
    >
      {/* Tab Bar */}
      <div style={{ display: "flex", gap: "4px", marginBottom: "16px", borderBottom: "1px solid var(--border)", paddingBottom: "8px" }}>
        {TAB_ORDER.map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            style={{
              padding: "6px 14px",
              borderRadius: "6px",
              fontSize: "13px",
              fontWeight: 600,
              backgroundColor: tab === activeTab ? "var(--accent)" : "transparent",
              color: tab === activeTab ? "#000000" : "var(--muted)",
              border: "none",
              cursor: "pointer",
              transition: "all 0.15s ease",
            }}
          >
            {TAB_LABELS[tab]}
          </button>
        ))}
      </div>

      {/* Metrics Grid */}
      {currentMetrics.length === 0 ? (
        <div style={{ textAlign: "center", color: "var(--muted)", fontSize: "14px", padding: "20px" }}>
          No data available for this tab.
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "12px" }}>
          {currentMetrics.map((metric) => (
            <div
              key={metric.label}
              style={{
                padding: "14px",
                borderRadius: "10px",
                backgroundColor: isDarkMode ? "rgba(255,255,255,0.03)" : "#f8fafc",
                border: "1px solid var(--border)",
              }}
            >
              <div
                style={{
                  fontSize: "11px",
                  fontWeight: 600,
                  color: "var(--muted)",
                  textTransform: "uppercase",
                  letterSpacing: "0.05em",
                  marginBottom: "6px",
                }}
              >
                {metric.label}
              </div>
              <div
                style={{
                  fontSize: "20px",
                  fontWeight: 700,
                  color: "var(--foreground)",
                  letterSpacing: "-0.02em",
                  marginBottom: "8px",
                }}
              >
                {metric.formatted}
              </div>
              <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
                <GrowthBadge value={metric.yoy} isDarkMode={isDarkMode} />
                <GrowthBadge value={metric.qoq} isDarkMode={isDarkMode} />
              </div>
            </div>
          ))}
        </div>
      )}

      {data.latest_quarter && (
        <div
          style={{
            marginTop: "12px",
            fontSize: "11px",
            color: "var(--subtle)",
            textAlign: "right",
          }}
        >
          Based on latest report: {data.latest_quarter}
        </div>
      )}
    </div>
  );
}
