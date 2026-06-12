import { useState, useCallback } from "react";
import { useTheme } from "../../context/ThemeContext";
import ControlPanel, { ScanParams } from "./components/ControlPanel";
import SectorRegimeGrid from "./components/SectorRegimeGrid";
import SignalsTable from "./components/SignalsTable";

interface SectorRegime {
  etf: string;
  regime: string;
  bull_probability: number;
  vol_regime: string;
}

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

export default function MarkovPage() {
  const { isDarkMode } = useTheme();
  const [loading, setLoading] = useState(false);
  const [sectors, setSectors] = useState<SectorRegime[]>([]);
  const [signals, setSignals] = useState<Signal[]>([]);
  const [totalScanned, setTotalScanned] = useState(0);
  const [error, setError] = useState<string | null>(null);

  // Theme-aware colors
  const colors = {
    error: "#EF4444",
    muted: isDarkMode ? "rgba(255,255,255,0.7)" : "#6e6e73",
  };

  const handleScan = useCallback(async (params: ScanParams) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/markov/scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: params.model,
          threshold: params.threshold,
          min_conviction: params.minConviction,
          max_results: params.maxResults,
        }),
      });
      if (!res.ok) {
        throw new Error(`Scan request failed: ${res.status} ${res.statusText}`);
      }
      const data = await res.json();
      if (data.signals != null) setSignals(data.signals);
      if (data.sector_status != null) setSectors(data.sector_status);
      if (data.total_scanned != null) setTotalScanned(data.total_scanned);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Scan failed");
    } finally {
      setLoading(false);
    }
  }, []);

  return (
    <div style={{ maxWidth: 1280, margin: "0 auto" }}>
      <ControlPanel onScan={handleScan} loading={loading} />

      {error && (
        <div style={{ padding: "12px 24px", color: colors.error, fontSize: 14 }}>
          Error: {error}
        </div>
      )}

      {sectors.length > 0 && <SectorRegimeGrid sectors={sectors} isDarkMode={isDarkMode} />}
      <SignalsTable signals={signals} totalScanned={totalScanned} loading={loading} isDarkMode={isDarkMode} />
    </div>
  );
}