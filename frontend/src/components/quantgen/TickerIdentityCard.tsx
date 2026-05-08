import { Building2, DollarSign, TrendingUp, Activity } from "lucide-react";

interface TickerIdentityCardProps {
  ticker: string;
  name?: string;
  sector?: string;
  industry?: string;
  marketCap?: number | null;
  beta?: number | null;
  latestPrice?: number | null;
  isDarkMode?: boolean;
}

function formatMarketCap(value: number | null | undefined): string {
  if (value == null) return "N/A";
  const absVal = Math.abs(value);
  if (absVal >= 1e12) return `$${(value / 1e12).toFixed(2)}T`;
  if (absVal >= 1e9) return `$${(value / 1e9).toFixed(1)}B`;
  if (absVal >= 1e6) return `$${(value / 1e6).toFixed(1)}M`;
  return `$${value.toLocaleString()}`;
}

export default function TickerIdentityCard({
  ticker,
  name,
  sector,
  industry,
  marketCap,
  beta,
  latestPrice,
  isDarkMode = true,
}: TickerIdentityCardProps) {
  const displayName = name || ticker.toUpperCase();
  const displaySector = sector || "Unknown";
  const displayIndustry = industry || "Unknown";

  return (
    <div
      style={{
        padding: "20px 24px",
        borderRadius: "14px",
        backgroundColor: "var(--surface)",
        border: "1px solid var(--border)",
        marginBottom: "24px",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "20px", flexWrap: "wrap" }}>
        {/* Ticker Badge */}
        <div
          style={{
            width: "56px",
            height: "56px",
            borderRadius: "12px",
            background: isDarkMode
              ? "linear-gradient(135deg, #10B981 0%, #059669 100%)"
              : "linear-gradient(135deg, #34D399 0%, #10B981 100%)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "#ffffff",
            fontSize: "18px",
            fontWeight: 700,
            flexShrink: 0,
            boxShadow: "0 2px 8px rgba(16,185,129,0.3)",
          }}
        >
          {ticker.toUpperCase()}
        </div>

        {/* Company Info */}
        <div style={{ flex: 1, minWidth: "200px" }}>
          <div
            style={{
              fontSize: "18px",
              fontWeight: 700,
              color: "var(--foreground)",
              letterSpacing: "-0.01em",
            }}
          >
            {displayName}
          </div>
          <div
            style={{
              fontSize: "13px",
              color: "var(--muted)",
              marginTop: "2px",
              display: "flex",
              alignItems: "center",
              gap: "6px",
            }}
          >
            <Building2 size={12} style={{ color: "var(--subtle)" }} />
            {displaySector}
            {displayIndustry !== displaySector && displayIndustry !== "Unknown" && (
              <>
                <span style={{ color: "var(--subtle)" }}>—</span>
                {displayIndustry}
              </>
            )}
          </div>
        </div>

        {/* Mini Stats */}
        <div style={{ display: "flex", gap: "24px", flexWrap: "wrap" }}>
          <div style={{ textAlign: "center", minWidth: "80px" }}>
            <div
              style={{
                fontSize: "11px",
                fontWeight: 600,
                color: "var(--muted)",
                textTransform: "uppercase",
                letterSpacing: "0.05em",
                marginBottom: "4px",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: "4px",
              }}
            >
              <DollarSign size={10} />
              Market Cap
            </div>
            <div
              style={{
                fontSize: "16px",
                fontWeight: 700,
                color: "var(--foreground)",
              }}
            >
              {formatMarketCap(marketCap)}
            </div>
          </div>

          <div style={{ textAlign: "center", minWidth: "60px" }}>
            <div
              style={{
                fontSize: "11px",
                fontWeight: 600,
                color: "var(--muted)",
                textTransform: "uppercase",
                letterSpacing: "0.05em",
                marginBottom: "4px",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: "4px",
              }}
            >
              <TrendingUp size={10} />
              Beta
            </div>
            <div
              style={{
                fontSize: "16px",
                fontWeight: 700,
                color: "var(--foreground)",
              }}
            >
              {beta != null ? beta.toFixed(2) : "N/A"}
            </div>
          </div>

          <div style={{ textAlign: "center", minWidth: "80px" }}>
            <div
              style={{
                fontSize: "11px",
                fontWeight: 600,
                color: "var(--muted)",
                textTransform: "uppercase",
                letterSpacing: "0.05em",
                marginBottom: "4px",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: "4px",
              }}
            >
              <Activity size={10} />
              Latest Close
            </div>
            <div
              style={{
                fontSize: "16px",
                fontWeight: 700,
                color: "var(--foreground)",
              }}
            >
              {latestPrice != null ? `$${latestPrice.toFixed(2)}` : "N/A"}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
