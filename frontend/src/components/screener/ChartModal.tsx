import { useState, useEffect } from "react";
import { X, BarChart3, Loader2 } from "lucide-react";
import { CandleStickChart } from "@/components/quantgen";

interface ChartModalProps {
  ticker: string | null;
  onClose: () => void;
  colors: {
    surface: string;
    border: string;
    text: string;
    muted: string;
    subtle: string;
    borderHover: string;
  };
}

const LABEL_STYLE: React.CSSProperties = {
  fontSize: "12px",
  fontWeight: 600,
  letterSpacing: "0.15em",
  textTransform: "uppercase",
  color: "rgba(255,255,255,0.4)",
};

export default function ChartModal({ ticker, onClose, colors }: ChartModalProps) {
  const [chartData, setChartData] = useState<any[]>([]);
  const [chartLoading, setChartLoading] = useState(false);
  const [chartIndicators, setChartIndicators] = useState<any>(null);

  useEffect(() => {
    if (!ticker) {
      setChartData([]);
      return;
    }
    setChartLoading(true);
    fetch(`/api/ohlcv/${ticker.toLowerCase()}`)
      .then((r) => r.json())
      .then((data) => {
        setChartData(data);
        setChartIndicators({ sma20: data.sma20, sma50: data.sma50 });
      })
      .catch(console.error)
      .finally(() => setChartLoading(false));
  }, [ticker]);

  if (!ticker) return null;

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 100,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        backgroundColor: "rgba(0,0,0,0.7)",
        backdropFilter: "blur(8px)",
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        style={{
          width: "95%",
          maxWidth: "1680px",
          maxHeight: "92vh",
          borderRadius: "20px",
          backgroundColor: colors.surface,
          border: `1px solid ${colors.border}`,
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        }}
      >
        {/* Modal Header */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "20px 24px",
            borderBottom: `1px solid ${colors.border}`,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
            <div
              style={{
                width: "36px",
                height: "36px",
                borderRadius: "10px",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                backgroundColor: "rgba(16,185,129,0.15)",
              }}
            >
              <BarChart3
                style={{ width: "18px", height: "18px", color: "#10B981" }}
              />
            </div>
            <div>
              <h3
                style={{
                  fontSize: "20px",
                  fontWeight: 600,
                  letterSpacing: "-0.02em",
                  color: colors.text,
                  margin: 0,
                }}
              >
                {ticker}
              </h3>
              <span style={{ ...LABEL_STYLE, fontSize: "11px" }}>
                Candlestick Chart
              </span>
            </div>
          </div>
          <button
            onClick={onClose}
            style={{
              width: "32px",
              height: "32px",
              borderRadius: "8px",
              border: `1px solid ${colors.border}`,
              backgroundColor: "transparent",
              color: colors.muted,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              cursor: "pointer",
              transition: "all 150ms ease",
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.borderColor = colors.borderHover;
              e.currentTarget.style.color = colors.text;
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.borderColor = colors.border;
              e.currentTarget.style.color = colors.muted;
            }}
          >
            <X style={{ width: "16px", height: "16px" }} />
          </button>
        </div>

        {/* Chart Body */}
        <div style={{ flex: 1, padding: "16px 24px 24px", minHeight: "735px" }}>
          {chartLoading ? (
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                height: "735px",
                gap: "12px",
              }}
            >
              <Loader2
                style={{
                  width: "24px",
                  height: "24px",
                  color: colors.muted,
                }}
                className="animate-spin"
              />
              <span style={{ ...LABEL_STYLE, fontSize: "13px" }}>
                Loading chart data...
              </span>
            </div>
          ) : chartData.length > 0 ? (
            <CandleStickChart
              data={chartData}
              height={735}
              indicators={chartIndicators}
            />
          ) : (
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                height: "735px",
                color: colors.subtle,
                fontSize: "15px",
              }}
            >
              No chart data available
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
