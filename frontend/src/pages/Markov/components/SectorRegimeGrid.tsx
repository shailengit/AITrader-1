interface SectorRegime {
  etf: string;
  regime: string;
  bull_probability: number;
  vol_regime: string;
}

interface SectorRegimeGridProps {
  sectors: SectorRegime[];
  isDarkMode: boolean;
}

export default function SectorRegimeGrid({ sectors, isDarkMode }: SectorRegimeGridProps) {
  if (!sectors || sectors.length === 0) return null;

  const muted = isDarkMode ? "rgba(255,255,255,0.7)" : "#6e6e73";
  const border = isDarkMode ? "rgba(255,255,255,0.12)" : "#d2d2d7";

  return (
    <div style={{ padding: "24px" }}>
      <h2 style={{ fontSize: 20, fontWeight: 600, marginBottom: 16 }}>
        Sector Regimes
      </h2>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 12 }}>
        {sectors.map((s) => (
          <div
            key={s.etf}
            style={{
              padding: 16,
              borderRadius: 12,
              border: `1px solid ${s.regime === "BULL" ? "#10B981" : s.regime === "BEAR" ? "#EF4444" : border}`,
              background: s.regime === "BULL" ? "rgba(16, 185, 129, 0.08)" : s.regime === "BEAR" ? "rgba(239, 68, 68, 0.08)" : "transparent",
            }}
          >
            <div style={{ fontSize: 16, fontWeight: 700 }}>{s.etf}</div>
            <div style={{ fontSize: 14, color: s.regime === "BULL" ? "#10B981" : "#EF4444", marginTop: 4 }}>
              {s.regime}
            </div>
            <div style={{ fontSize: 12, color: muted, marginTop: 2 }}>
              Bull: {(s.bull_probability * 100).toFixed(0)}% | Vol: {s.vol_regime}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}