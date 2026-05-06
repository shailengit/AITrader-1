import { useState, useEffect, useMemo } from "react";
import {
  Search,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Sparkles,
  ChevronDown,
  Zap,
  BarChart3,
  SlidersHorizontal,
  Cpu,
  FileDown,
  Terminal,
  X,
} from "lucide-react";
import { AnimatePresence } from "framer-motion";
import { useTheme } from "../context/ThemeContext";
import TerminalLog from "../components/screener/TerminalLog";
import { CandleStickChart } from "../components/quantgen/CandleStickChart";

interface ScanResult {
  ticker: string;
  company_name?: string;
  sector?: string;
  signal?: string;
  fundamental_catalyst?: string;
  close?: number;
  data_date?: string;
  sma_20?: number;
  sma_50?: number;
  rsi?: number;
  macd?: number;
  volume?: number;
  volume_ma_50?: number;
  ema_9?: number;
  high_52w?: number;
  low_52w?: number;
  all_time_high?: number;
  all_time_low?: number;
  ath_proximity?: number;
  volume_ratio?: number;
  eps_growth_qoq?: number;
  revenue_growth_qoq?: number;
  peg_ratio?: number;
  market_cap?: number;
  beta?: number;
}

interface ScanStatus {
  scan_id: string;
  mode: string;
  status: "pending" | "running" | "completed" | "failed";
  progress: number;
  use_ai: boolean;
  results_count: number;
  has_ai_report: boolean;
  error?: string;
}

interface ScreenerMode {
  id: string;
  name: string;
  description: string;
  agents: string[];
  supports_backtesting: boolean;
}

interface LogEntry {
  agent: string;
  message: string;
  type: string;
  color: string;
}

const SECTION_HEADING: React.CSSProperties = {
  fontSize: '28px',
  fontWeight: 600,
  letterSpacing: '-0.02em',
  lineHeight: 1.14,
  color: '#FAFAFA',
};

const BODY_TEXT: React.CSSProperties = {
  fontSize: '17px',
  fontWeight: 400,
  lineHeight: 1.47,
  letterSpacing: '-0.022em',
  color: 'rgba(255,255,255,0.7)',
};

const LABEL_STYLE: React.CSSProperties = {
  fontSize: '12px',
  fontWeight: 600,
  letterSpacing: '0.15em',
  textTransform: 'uppercase',
  color: 'rgba(255,255,255,0.4)',
};

const SCREENER_STATE_KEY = 'screener:lastScan';

export default function StockScreener() {
  const { isDarkMode } = useTheme();
  const [modes, setModes] = useState<ScreenerMode[]>([]);
  const [selectedMode, setSelectedMode] = useState<string>("dormant_giant");
  const [useAi, setUseAi] = useState(true);
  const [cutoffDate, setCutoffDate] = useState<string>("");
  const [customPrompt, setCustomPrompt] = useState<string>("");
  const [scanStatus, setScanStatus] = useState<ScanStatus | null>(null);
  const [isScanning, setIsScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<ScanResult[]>([]);
  const [aiReport, setAiReport] = useState<string | null>(null);
  const [showReport, setShowReport] = useState(false);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [showTerminal, setShowTerminal] = useState(false);
  const [progress, setProgress] = useState(0);
  const [filters, setFilters] = useState({
    squeeze_threshold: 1.5,
    accumulation_threshold: 0.01,
    volume_threshold: 1.2,
  });
  const [quantFilters, setQuantFilters] = useState<Record<string, any> | null>(null);
  const [isParsingFilters, setIsParsingFilters] = useState(false);
  const [lastUpdated] = useState<string>(new Date().toLocaleTimeString());

  // Chart modal state
  const [chartTicker, setChartTicker] = useState<string | null>(null);
  const [chartData, setChartData] = useState<any[]>([]);
  const [chartLoading, setChartLoading] = useState(false);

  const colors = {
    text: isDarkMode ? '#FAFAFA' : '#1d1d1f',
    muted: isDarkMode ? 'rgba(255,255,255,0.7)' : 'rgba(0,0,0,0.8)',
    subtle: isDarkMode ? 'rgba(255,255,255,0.4)' : 'rgba(0,0,0,0.48)',
    border: isDarkMode ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.04)',
    borderHover: isDarkMode ? 'rgba(255,255,255,0.15)' : 'rgba(0,0,0,0.1)',
    surface: isDarkMode ? '#0a0a0a' : '#ffffff',
    surfaceRaised: isDarkMode ? '#111111' : '#fafafc',
    inputBg: isDarkMode ? '#000000' : '#ffffff',
    canvas: isDarkMode ? '#050505' : '#f5f5f7',
  };

  useEffect(() => {
    fetch("/api/screener/modes")
      .then((res) => res.json())
      .then((data) => setModes(data.modes))
      .catch((err) => console.error("Failed to fetch modes:", err));
  }, []);

  // Restore persisted scan state on mount
  useEffect(() => {
    try {
      const saved = localStorage.getItem(SCREENER_STATE_KEY);
      if (saved) {
        const state = JSON.parse(saved);
        const isFresh = state.timestamp && (Date.now() - state.timestamp) < 24 * 60 * 60 * 1000;
        if (isFresh) {
          setResults(state.results || []);
          setScanStatus(state.scanStatus || null);
          setAiReport(state.aiReport || null);
          setLogs(state.logs || []);
          setProgress(state.progress || 0);
          if (state.selectedMode) setSelectedMode(state.selectedMode);
          if (state.useAi !== undefined) setUseAi(state.useAi);
        }
      }
    } catch { /* ignore */ }
  }, []);

  // Persist scan state whenever results/status/logs update
  useEffect(() => {
    if (results.length > 0 || aiReport || scanStatus) {
      const state = {
        results,
        scanStatus,
        aiReport,
        logs,
        progress,
        selectedMode,
        useAi,
        timestamp: Date.now(),
      };
      try { localStorage.setItem(SCREENER_STATE_KEY, JSON.stringify(state)); } catch { /* ignore */ }
    }
  }, [results, scanStatus, aiReport, logs, progress, selectedMode, useAi]);

  // Keyboard shortcut: s to start scan
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 's' && !isScanning && !e.target || (e.target as HTMLElement).tagName !== 'INPUT' && (e.target as HTMLElement).tagName !== 'TEXTAREA') {
        if (!isScanning) startScan();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isScanning, selectedMode, useAi, customPrompt, filters]);

  const clearResults = () => {
    setResults([]);
    setScanStatus(null);
    setAiReport(null);
    setLogs([]);
    setProgress(0);
    setShowReport(false);
    setQuantFilters(null);
    try { localStorage.removeItem(SCREENER_STATE_KEY); } catch { /* ignore */ }
  };

  // Clear quant filters when switching away from quant_strategy mode
  useEffect(() => {
    if (selectedMode !== "quant_strategy") {
      setQuantFilters(null);
    }
  }, [selectedMode]);

  const openChart = async (ticker: string) => {
    setChartTicker(ticker);
    setChartLoading(true);
    setChartData([]);
    try {
      const res = await fetch(`/api/ohlcv/${ticker.toLowerCase()}`);
      const data = await res.json();
      setChartData(data);
    } catch (err) {
      console.error('Failed to fetch chart data:', err);
    } finally {
      setChartLoading(false);
    }
  };

  const closeChart = () => {
    setChartTicker(null);
    setChartData([]);
  };

  // Compute SMA-20 and EMA-9 from chart data for the candlestick modal
  const chartIndicators = useMemo(() => {
    if (!chartData.length) return [];

    const sorted = [...chartData].sort((a, b) => a.time - b.time);
    const closes = sorted.map((d) => d.close);

    // SMA-20
    const sma20 = sorted.map((d, i) => {
      if (i < 19) return null;
      const sum = closes.slice(i - 19, i + 1).reduce((a, b) => a + b, 0);
      return { time: d.time, value: sum / 20 };
    }).filter((d): d is { time: number; value: number } => d !== null);

    // EMA-9
    const ema9: { time: number; value: number }[] = [];
    const multiplier = 2 / (9 + 1);
    for (let i = 0; i < sorted.length; i++) {
      if (i < 8) continue;
      if (ema9.length === 0) {
        const seed = closes.slice(0, 9).reduce((a, b) => a + b, 0) / 9;
        ema9.push({ time: sorted[i].time, value: seed });
      } else {
        const prevEma = ema9[ema9.length - 1].value;
        const ema = closes[i] * multiplier + prevEma * (1 - multiplier);
        ema9.push({ time: sorted[i].time, value: ema });
      }
    }

    return [
      { name: 'SMA 20', type: 'line', data: sma20, color: '#ef4444', lineWidth: 3 },
      { name: 'EMA 9', type: 'line', data: ema9, color: '#3b82f6', lineWidth: 3 },
    ];
  }, [chartData]);

  const generateFilters = async () => {
    if (!customPrompt.trim()) {
      setError("Please enter a custom directive first.");
      return;
    }
    setIsParsingFilters(true);
    setError(null);
    try {
      const res = await fetch("/api/screener/parse-filters", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: customPrompt }),
      });
      if (!res.ok) throw new Error("Failed to parse filters");
      const data = await res.json();
      setQuantFilters(data.filters || {});
    } catch (err) {
      setError(err instanceof Error ? err.message : "Filter parsing failed");
    } finally {
      setIsParsingFilters(false);
    }
  };

  const startScan = async () => {
    setIsScanning(true);
    setError(null);
    setResults([]);
    setAiReport(null);
    setShowReport(false);
    setLogs([]);
    setProgress(0);

    try {
      const res = await fetch("/api/screener/scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          mode: selectedMode,
          use_ai: useAi,
          cutoff_date: cutoffDate || undefined,
          prompt: customPrompt || undefined,
          max_results: 50,
          filters: selectedMode === "dormant_giant" ? filters : quantFilters || undefined,
        }),
      });

      if (!res.ok) throw new Error("Failed to start scan");

      const data = await res.json();
      const scanId = data.scan_id;

      const eventSource = new EventSource(`/api/screener/stream/${scanId}`);

      eventSource.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          const { type, data: eventData } = payload;

          if (type === "progress") {
            setProgress(eventData.progress);
            setScanStatus((prev) =>
              prev ? { ...prev, progress: eventData.progress } : null
            );
          } else if (type === "log") {
            setLogs((prev) => [...prev, eventData]);
          } else if (type === "status") {
            setScanStatus((prev) =>
              prev ? { ...prev, status: eventData.status, progress: eventData.progress ?? prev.progress } : null
            );
            if (eventData.status === "completed") {
              setIsScanning(false);
              setProgress(100);
              fetchResults(scanId);
              eventSource.close();
            } else if (eventData.status === "failed") {
              setIsScanning(false);
              setError(eventData.error || "Scan failed");
              eventSource.close();
            }
          }
        } catch (e) {
          console.error("Failed to parse SSE event:", e);
        }
      };

      eventSource.onerror = () => {
        eventSource.close();
        pollScanStatusFallback(scanId);
      };

      setScanStatus({
        scan_id: scanId,
        mode: selectedMode,
        status: "running",
        progress: 0,
        use_ai: useAi,
        results_count: 0,
        has_ai_report: false,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
      setIsScanning(false);
    }
  };

  const fetchResults = async (id: string) => {
    try {
      const res = await fetch(`/api/screener/results/${id}`);
      const data = await res.json();
      setResults(data.results || []);

      if (data.has_ai_report) {
        const reportRes = await fetch(`/api/screener/ai-report/${id}`);
        const reportData = await reportRes.json();
        setAiReport(reportData.ai_report);
      }
    } catch (err) {
      console.error("Failed to fetch results:", err);
    }
  };

  const pollScanStatusFallback = async (id: string) => {
    const poll = async () => {
      try {
        const res = await fetch(`/api/screener/status/${id}`);
        const data = await res.json();

        setScanStatus(data);
        setProgress(data.progress);
        if (data.logs) {
          setLogs((prev) => {
            const existingKeys = new Set(prev.map((l) => l.message));
            const newLogs = data.logs.filter((l: LogEntry) => !existingKeys.has(l.message));
            return [...prev, ...newLogs];
          });
        }

        if (data.status === "running") {
          setTimeout(poll, 1000);
        } else if (data.status === "completed") {
          setIsScanning(false);
          setProgress(100);
          fetchResults(id);
        } else if (data.status === "failed") {
          setIsScanning(false);
          setError(data.error || "Scan failed");
        }
      } catch {
        setIsScanning(false);
        setError("Failed to get scan status");
      }
    };
    poll();
  };

  const downloadPDF = () => {
    if (!scanStatus) return;
    window.open(`/api/screener/report/${scanStatus.scan_id}`, "_blank");
  };

  return (
    <div className="min-h-screen" style={{ backgroundColor: colors.canvas }}>
      <div style={{ maxWidth: '1280px', padding: '0 32px', margin: '0 auto' }}>

        {/* === HEADER === */}
        <div style={{ paddingTop: '64px', paddingBottom: '48px', textAlign: 'center' }}>
          <h1 style={{
            fontSize: '32px',
            fontWeight: 600,
            letterSpacing: '-0.02em',
            lineHeight: 1.14,
            color: colors.text,
            marginBottom: '8px',
          }}>
            AI Stock Screener
          </h1>
          <p style={{ ...BODY_TEXT, maxWidth: '600px', margin: '0 auto' }}>
            Multi-agent technical and fundamental screening powered by intelligent agents
          </p>
        </div>

        {/* === MODE SELECTION === */}
        <section style={{ marginBottom: '48px' }}>
          <h2 style={{ ...SECTION_HEADING, marginBottom: '24px', textAlign: 'center' }}>Select Mode</h2>

          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(2, 1fr)',
            gap: '24px',
          }}>
            {modes.map((mode) => {
              const isSelected = selectedMode === mode.id;
              const Icon = mode.id === "dormant_giant" ? Zap : BarChart3;

              return (
                <button
                  key={mode.id}
                  onClick={() => setSelectedMode(mode.id)}
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    textAlign: 'center',
                    padding: '32px',
                    borderRadius: '20px',
                    backgroundColor: isSelected ? colors.surfaceRaised : 'transparent',
                    border: `1px solid ${isSelected ? 'rgba(16,185,129,0.5)' : colors.border}`,
                    cursor: 'pointer',
                    transition: 'all 150ms ease',
                    position: 'relative',
                    gap: '16px',
                  }}
                  onMouseEnter={(e) => {
                    if (!isSelected) {
                      e.currentTarget.style.backgroundColor = colors.surface;
                      e.currentTarget.style.borderColor = colors.borderHover;
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (!isSelected) {
                      e.currentTarget.style.backgroundColor = 'transparent';
                      e.currentTarget.style.borderColor = colors.border;
                    }
                  }}
                >
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '12px', width: '100%' }}>
                    <div style={{
                      width: '40px',
                      height: '40px',
                      borderRadius: '10px',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      backgroundColor: isSelected ? 'rgba(16,185,129,0.15)' : 'rgba(255,255,255,0.05)',
                      transition: 'background-color 150ms ease',
                    }}>
                      <Icon style={{
                        width: '20px',
                        height: '20px',
                        color: isSelected ? '#10B981' : 'rgba(255,255,255,0.4)',
                      }} />
                    </div>
                    <h3 style={{
                      fontSize: '21px',
                      fontWeight: 600,
                      letterSpacing: '-0.02em',
                      color: isSelected ? colors.text : colors.subtle,
                      transition: 'color 150ms ease',
                    }}>
                      {mode.name}
                    </h3>
                  </div>

                  <p style={{
                    ...BODY_TEXT,
                    fontSize: '15px',
                    color: isSelected ? colors.muted : colors.subtle,
                    margin: 0,
                    textAlign: 'center',
                  }}>
                    {mode.description}
                  </p>

                  {mode.agents.length > 0 && (
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '8px', justifyContent: 'center' }}>
                      {mode.agents.slice(0, 4).map((agent) => (
                        <span key={agent} style={{
                          fontSize: '11px',
                          fontWeight: 600,
                          letterSpacing: '0.05em',
                          padding: '4px 12px',
                          borderRadius: '999px',
                          backgroundColor: isSelected ? 'rgba(16,185,129,0.1)' : 'rgba(255,255,255,0.04)',
                          color: isSelected ? '#10B981' : colors.subtle,
                          border: `1px solid ${isSelected ? 'rgba(16,185,129,0.2)' : 'transparent'}`,
                        }}>
                          {agent}
                        </span>
                      ))}
                    </div>
                  )}
                </button>
              );
            })}
          </div>
        </section>

        {/* === CONFIGURATION === */}
        <section style={{ marginBottom: '48px' }}>
          <h2 style={{ ...SECTION_HEADING, marginBottom: '24px', textAlign: 'center' }}>Configuration</h2>

          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(2, 1fr)',
            gap: '24px',
          }}>
            {/* AI Analysis */}
            <div style={{
              padding: '32px',
              borderRadius: '20px',
              border: `1px solid ${colors.border}`,
              backgroundColor: colors.surface,
            }}>
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '12px', marginBottom: '20px' }}>
                <div style={{
                  width: '36px',
                  height: '36px',
                  borderRadius: '10px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  backgroundColor: useAi ? 'rgba(16,185,129,0.15)' : 'rgba(255,255,255,0.05)',
                }}>
                  <Cpu style={{
                    width: '18px',
                    height: '18px',
                    color: useAi ? '#10B981' : colors.subtle,
                  }} />
                </div>
                <div style={{ textAlign: 'center' }}>
                  <span style={{
                    fontSize: '17px',
                    fontWeight: 600,
                    letterSpacing: '-0.022em',
                    color: colors.text,
                  }}>AI Analysis</span>
                  <span style={{ ...LABEL_STYLE, display: 'block', marginTop: '2px' }}>
                    {useAi ? 'Enabled' : 'Disabled'}
                  </span>
                </div>
                <button
                  onClick={() => setUseAi(!useAi)}
                  style={{
                    width: '44px',
                    height: '24px',
                    borderRadius: '12px',
                    border: 'none',
                    backgroundColor: useAi ? '#10B981' : 'rgba(255,255,255,0.15)',
                    cursor: 'pointer',
                    position: 'relative',
                    transition: 'background-color 150ms ease',
                    flexShrink: 0,
                  }}
                  aria-label={`Toggle AI analysis ${useAi ? 'off' : 'on'}`}
                >
                  <div style={{
                    position: 'absolute',
                    top: '2px',
                    width: '20px',
                    height: '20px',
                    borderRadius: '50%',
                    backgroundColor: '#fff',
                    transition: 'transform 150ms ease',
                    transform: useAi ? 'translateX(20px)' : 'translateX(2px)',
                    boxShadow: '0 1px 3px rgba(0,0,0,0.3)',
                  }} />
                </button>
              </div>

              <div style={{ textAlign: 'center', marginBottom: '20px' }}>
                <label style={{ ...LABEL_STYLE, display: 'block', marginBottom: '8px' }}>
                  Cutoff Date
                </label>
                <input
                  type="date"
                  value={cutoffDate}
                  onChange={(e) => setCutoffDate(e.target.value)}
                  max={new Date().toISOString().split('T')[0]}
                  style={{
                    width: '100%',
                    padding: '10px 14px',
                    borderRadius: '10px',
                    border: `1px solid ${colors.border}`,
                    backgroundColor: colors.inputBg,
                    color: colors.text,
                    fontSize: '14px',
                    outline: 'none',
                    transition: 'border-color 150ms ease',
                  }}
                  onFocus={(e) => e.currentTarget.style.borderColor = 'rgba(16,185,129,0.5)'}
                  onBlur={(e) => e.currentTarget.style.borderColor = colors.border}
                />
                <span style={{ ...LABEL_STYLE, display: 'block', marginTop: '4px' }}>
                  {cutoffDate ? 'Screen as of this date' : 'Leave blank for latest data'}
                </span>
              </div>

              <div style={{ textAlign: 'center' }}>
                <label style={{ ...LABEL_STYLE, display: 'block', marginBottom: '8px' }}>
                  Custom Directives
                </label>
                <textarea
                  value={customPrompt}
                  onChange={(e) => setCustomPrompt(e.target.value)}
                  placeholder={
                    selectedMode === "dormant_giant"
                      ? "Begin the daily Dormant Giant screening workflow..."
                      : "Find me candidates for a high-growth breakout..."
                  }
                  style={{
                    width: '100%',
                    height: '120px',
                    padding: '16px',
                    borderRadius: '14px',
                    border: `1px solid ${colors.border}`,
                    backgroundColor: colors.inputBg,
                    color: colors.text,
                    fontSize: '14px',
                    fontFamily: 'JetBrains Mono, Fira Code, monospace',
                    lineHeight: 1.5,
                    resize: 'vertical',
                    outline: 'none',
                    transition: 'border-color 150ms ease',
                  }}
                  onFocus={(e) => e.currentTarget.style.borderColor = 'rgba(16,185,129,0.5)'}
                  onBlur={(e) => e.currentTarget.style.borderColor = colors.border}
                />

                {/* Generate Filters button for Quant Strategy */}
                {selectedMode === "quant_strategy" && (
                  <button
                    onClick={generateFilters}
                    disabled={isParsingFilters || !customPrompt.trim()}
                    style={{
                      marginTop: '12px',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: '8px',
                      width: '100%',
                      padding: '10px 0',
                      borderRadius: '10px',
                      border: 'none',
                      backgroundColor: isParsingFilters ? colors.subtle : '#3B82F6',
                      color: '#fff',
                      fontSize: '14px',
                      fontWeight: 600,
                      cursor: isParsingFilters || !customPrompt.trim() ? 'not-allowed' : 'pointer',
                      opacity: isParsingFilters || !customPrompt.trim() ? 0.5 : 1,
                      transition: 'all 150ms ease',
                    }}
                  >
                    {isParsingFilters ? (
                      <>
                        <Loader2 style={{ width: '16px', height: '16px', animation: 'spin 1s linear infinite' }} />
                        Parsing Filters...
                      </>
                    ) : (
                      <>
                        <Sparkles style={{ width: '16px', height: '16px' }} />
                        Generate Filters from Prompt
                      </>
                    )}
                  </button>
                )}

                {/* Filter Review Panel */}
                {selectedMode === "quant_strategy" && quantFilters && (
                  <div style={{
                    marginTop: '16px',
                    padding: '20px',
                    borderRadius: '14px',
                    border: `1px solid ${colors.border}`,
                    backgroundColor: colors.inputBg,
                    textAlign: 'left',
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
                      <span style={{ ...LABEL_STYLE, fontSize: '11px' }}>Parsed Filters — Edit before scanning</span>
                      <button
                        onClick={() => setQuantFilters(null)}
                        style={{
                          background: 'none',
                          border: 'none',
                          color: colors.subtle,
                          fontSize: '12px',
                          cursor: 'pointer',
                        }}
                      >
                        Clear
                      </button>
                    </div>

                    {/* ATH Proximity */}
                    <div style={{ marginBottom: '12px' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                        <span style={{ fontSize: '13px', color: colors.muted }}>ATH Proximity Min</span>
                        <span style={{ fontSize: '13px', fontWeight: 600, color: '#10B981' }}>
                          {quantFilters.ath_proximity_min != null ? quantFilters.ath_proximity_min.toFixed(2) : 'Any'}
                        </span>
                      </div>
                      <input
                        type="range"
                        min={0.5}
                        max={1.0}
                        step={0.01}
                        value={quantFilters.ath_proximity_min ?? 0.5}
                        onChange={(e) => setQuantFilters({ ...quantFilters, ath_proximity_min: parseFloat(e.target.value) })}
                        style={{ width: '100%', height: '4px', appearance: 'none', backgroundColor: 'rgba(255,255,255,0.1)', borderRadius: '2px' }}
                      />
                    </div>

                    {/* RSI Range */}
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '12px' }}>
                      <div>
                        <span style={{ fontSize: '13px', color: colors.muted, display: 'block', marginBottom: '4px' }}>RSI Min</span>
                        <input
                          type="number"
                          min={0}
                          max={100}
                          value={quantFilters.rsi_min ?? ''}
                          onChange={(e) => setQuantFilters({ ...quantFilters, rsi_min: e.target.value ? parseFloat(e.target.value) : undefined })}
                          placeholder="Any"
                          style={{
                            width: '100%',
                            padding: '8px 10px',
                            borderRadius: '8px',
                            border: `1px solid ${colors.border}`,
                            backgroundColor: colors.surface,
                            color: colors.text,
                            fontSize: '14px',
                          }}
                        />
                      </div>
                      <div>
                        <span style={{ fontSize: '13px', color: colors.muted, display: 'block', marginBottom: '4px' }}>RSI Max</span>
                        <input
                          type="number"
                          min={0}
                          max={100}
                          value={quantFilters.rsi_max ?? ''}
                          onChange={(e) => setQuantFilters({ ...quantFilters, rsi_max: e.target.value ? parseFloat(e.target.value) : undefined })}
                          placeholder="Any"
                          style={{
                            width: '100%',
                            padding: '8px 10px',
                            borderRadius: '8px',
                            border: `1px solid ${colors.border}`,
                            backgroundColor: colors.surface,
                            color: colors.text,
                            fontSize: '14px',
                          }}
                        />
                      </div>
                    </div>

                    {/* Volume Ratio */}
                    <div style={{ marginBottom: '12px' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                        <span style={{ fontSize: '13px', color: colors.muted }}>Volume Ratio Min</span>
                        <span style={{ fontSize: '13px', fontWeight: 600, color: '#10B981' }}>
                          {quantFilters.volume_ratio_min != null ? quantFilters.volume_ratio_min.toFixed(2) : 'Any'}
                        </span>
                      </div>
                      <input
                        type="range"
                        min={0.5}
                        max={5.0}
                        step={0.1}
                        value={quantFilters.volume_ratio_min ?? 0.5}
                        onChange={(e) => setQuantFilters({ ...quantFilters, volume_ratio_min: parseFloat(e.target.value) })}
                        style={{ width: '100%', height: '4px', appearance: 'none', backgroundColor: 'rgba(255,255,255,0.1)', borderRadius: '2px' }}
                      />
                    </div>

                    {/* SMA Relations */}
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '12px' }}>
                      {[
                        { key: 'sma_20_relation', label: 'SMA(20)' },
                        { key: 'sma_50_relation', label: 'SMA(50)' },
                      ].map((item) => (
                        <div key={item.key}>
                          <span style={{ fontSize: '13px', color: colors.muted, display: 'block', marginBottom: '4px' }}>{item.label}</span>
                          <select
                            value={quantFilters[item.key] || 'any'}
                            onChange={(e) => setQuantFilters({ ...quantFilters, [item.key]: e.target.value })}
                            style={{
                              width: '100%',
                              padding: '8px 10px',
                              borderRadius: '8px',
                              border: `1px solid ${colors.border}`,
                              backgroundColor: colors.surface,
                              color: colors.text,
                              fontSize: '14px',
                            }}
                          >
                            <option value="any">Any</option>
                            <option value="above">Price Above</option>
                            <option value="below">Price Below</option>
                          </select>
                        </div>
                      ))}
                    </div>

                    {/* Sort By & Order */}
                    <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '12px', marginBottom: '12px' }}>
                      <div>
                        <span style={{ fontSize: '13px', color: colors.muted, display: 'block', marginBottom: '4px' }}>Sort By</span>
                        <select
                          value={quantFilters.sort_by || 'ticker'}
                          onChange={(e) => setQuantFilters({ ...quantFilters, sort_by: e.target.value })}
                          style={{
                            width: '100%',
                            padding: '8px 10px',
                            borderRadius: '8px',
                            border: `1px solid ${colors.border}`,
                            backgroundColor: colors.surface,
                            color: colors.text,
                            fontSize: '14px',
                          }}
                        >
                          <option value="ticker">Ticker</option>
                          <option value="ath_proximity">ATH Proximity</option>
                          <option value="rsi">RSI</option>
                          <option value="volume_ratio">Volume Ratio</option>
                          <option value="close">Close Price</option>
                        </select>
                      </div>
                      <div>
                        <span style={{ fontSize: '13px', color: colors.muted, display: 'block', marginBottom: '4px' }}>Order</span>
                        <select
                          value={quantFilters.sort_order || 'asc'}
                          onChange={(e) => setQuantFilters({ ...quantFilters, sort_order: e.target.value })}
                          style={{
                            width: '100%',
                            padding: '8px 10px',
                            borderRadius: '8px',
                            border: `1px solid ${colors.border}`,
                            backgroundColor: colors.surface,
                            color: colors.text,
                            fontSize: '14px',
                          }}
                        >
                          <option value="asc">Asc</option>
                          <option value="desc">Desc</option>
                        </select>
                      </div>
                    </div>

                    {/* Max Results */}
                    <div style={{ marginBottom: '8px' }}>
                      <span style={{ fontSize: '13px', color: colors.muted, display: 'block', marginBottom: '4px' }}>Max Results</span>
                      <input
                        type="number"
                        min={1}
                        max={100}
                        value={quantFilters.max_results || 20}
                        onChange={(e) => setQuantFilters({ ...quantFilters, max_results: parseInt(e.target.value, 10) })}
                        style={{
                          width: '100%',
                          padding: '8px 10px',
                          borderRadius: '8px',
                          border: `1px solid ${colors.border}`,
                          backgroundColor: colors.surface,
                          color: colors.text,
                          fontSize: '14px',
                        }}
                      />
                    </div>

                    {/* Live Summary */}
                    <div style={{
                      marginTop: '12px',
                      padding: '10px',
                      borderRadius: '8px',
                      backgroundColor: 'rgba(16,185,129,0.1)',
                      fontSize: '13px',
                      color: '#10B981',
                      lineHeight: 1.4,
                    }}>
                      <strong>Active filters:</strong>{' '}
                      {quantFilters.ath_proximity_min != null && `ATH ≥ ${(quantFilters.ath_proximity_min * 100).toFixed(0)}% `}
                      {quantFilters.rsi_min != null && `RSI ≥ ${quantFilters.rsi_min} `}
                      {quantFilters.rsi_max != null && `RSI ≤ ${quantFilters.rsi_max} `}
                      {quantFilters.volume_ratio_min != null && `Vol ≥ ${quantFilters.volume_ratio_min}x `}
                      {quantFilters.sma_20_relation && quantFilters.sma_20_relation !== 'any' && `SMA20 ${quantFilters.sma_20_relation} `}
                      {quantFilters.sma_50_relation && quantFilters.sma_50_relation !== 'any' && `SMA50 ${quantFilters.sma_50_relation} `}
                      | Sort: {quantFilters.sort_by || 'ticker'} {quantFilters.sort_order || 'asc'}
                      | Max: {quantFilters.max_results || 20}
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Thresholds - Conditional */}
            <div style={{
              padding: '32px',
              borderRadius: '20px',
              border: `1px solid ${colors.border}`,
              backgroundColor: colors.surface,
              opacity: selectedMode === 'dormant_giant' ? 1 : 0.4,
              transition: 'opacity 200ms ease',
            }}>
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '12px', marginBottom: '24px' }}>
                <div style={{
                  width: '36px',
                  height: '36px',
                  borderRadius: '10px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  backgroundColor: 'rgba(255,255,255,0.05)',
                }}>
                  <SlidersHorizontal style={{ width: '18px', height: '18px', color: colors.subtle }} />
                </div>
                <div style={{ textAlign: 'center' }}>
                  <span style={{
                    fontSize: '17px',
                    fontWeight: 600,
                    letterSpacing: '-0.022em',
                    color: colors.text,
                  }}>Thresholds</span>
                  {selectedMode !== 'dormant_giant' && (
                    <span style={{ ...LABEL_STYLE, display: 'block', marginTop: '2px' }}>
                      Dormant Giant only
                    </span>
                  )}
                </div>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
                {[
                  { key: "squeeze_threshold" as const, label: "Volatility Squeeze", min: 1.0, max: 2.0, step: 0.01 },
                  { key: "accumulation_threshold" as const, label: "Accumulation Force", min: 0.001, max: 0.02, step: 0.001 },
                  { key: "volume_threshold" as const, label: "Relative Volume", min: 1.0, max: 3.0, step: 0.1 }
                ].map((slider) => (
                  <div key={slider.key}>
                    <div style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      marginBottom: '8px',
                    }}>
                      <span style={LABEL_STYLE}>{slider.label}</span>
                      <span style={{
                        fontSize: '17px',
                        fontWeight: 600,
                        fontVariantNumeric: 'tabular-nums',
                        color: '#10B981',
                      }}>
                        {filters[slider.key].toFixed(slider.key === 'accumulation_threshold' ? 3 : 2)}
                      </span>
                    </div>
                    <input
                      type="range"
                      min={slider.min}
                      max={slider.max}
                      step={slider.step}
                      value={filters[slider.key]}
                      onChange={(e) => setFilters({ ...filters, [slider.key]: parseFloat(e.target.value) })}
                      disabled={selectedMode !== 'dormant_giant'}
                      style={{
                        width: '100%',
                        height: '4px',
                        appearance: 'none',
                        backgroundColor: selectedMode === 'dormant_giant' ? 'rgba(255,255,255,0.1)' : 'rgba(255,255,255,0.05)',
                        borderRadius: '2px',
                        outline: 'none',
                        cursor: selectedMode === 'dormant_giant' ? 'pointer' : 'not-allowed',
                      }}
                    />
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        {/* === ACTION BAR === */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '16px',
          marginBottom: '48px',
        }}>
          <button
            onClick={startScan}
            disabled={isScanning}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              padding: '14px 32px',
              borderRadius: '999px',
              border: 'none',
              backgroundColor: isScanning ? colors.subtle : '#10B981',
              color: isScanning ? colors.text : '#000000',
              fontSize: '17px',
              fontWeight: 600,
              letterSpacing: '-0.022em',
              cursor: isScanning ? 'not-allowed' : 'pointer',
              transition: 'all 150ms ease',
              opacity: isScanning ? 0.6 : 1,
            }}
            onMouseEnter={(e) => {
              if (!isScanning) {
                e.currentTarget.style.backgroundColor = '#34D399';
                e.currentTarget.style.transform = 'translateY(-1px)';
              }
            }}
            onMouseLeave={(e) => {
              if (!isScanning) {
                e.currentTarget.style.backgroundColor = '#10B981';
                e.currentTarget.style.transform = 'translateY(0)';
              }
            }}
          >
            {isScanning ? (
              <Loader2 style={{ width: '18px', height: '18px' }} className="animate-spin" />
            ) : (
              <Search style={{ width: '18px', height: '18px' }} />
            )}
            {isScanning ? `Scanning... ${progress}%` : 'Start Screen'}
          </button>

          {isScanning && (
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
            }}>
              <div style={{
                width: '160px',
                height: '4px',
                borderRadius: '2px',
                backgroundColor: 'rgba(255,255,255,0.08)',
                overflow: 'hidden',
              }}>
                <div style={{
                  width: `${progress}%`,
                  height: '100%',
                  backgroundColor: '#10B981',
                  borderRadius: '2px',
                  transition: 'width 300ms ease',
                }} />
              </div>
              <span style={{ ...LABEL_STYLE }}>{progress}%</span>
            </div>
          )}

          {/* Terminal toggle */}
          <button
            onClick={() => setShowTerminal(!showTerminal)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '8px 16px',
              borderRadius: '14px',
              border: `1px solid ${colors.border}`,
              backgroundColor: 'transparent',
              color: colors.muted,
              fontSize: '13px',
              fontWeight: 600,
              cursor: 'pointer',
              transition: 'all 150ms ease',
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
            <Terminal style={{ width: '14px', height: '14px' }} />
            {showTerminal ? 'Hide Logs' : 'Show Logs'}
          </button>
        </div>

        {/* === TERMINAL: xterm.js === */}
        <AnimatePresence>
          {showTerminal && (
            <TerminalLog
              logs={logs}
              style={{
                marginBottom: '32px',
                borderRadius: '14px',
                overflow: 'hidden',
                border: `1px solid ${colors.border}`,
                maxHeight: '320px',
              }}
            />
          )}
        </AnimatePresence>

        {/* === RESULTS === */}
        {(results.length > 0 || aiReport) && (
          <div style={{
            paddingTop: '48px',
            borderTop: `1px solid ${colors.border}`,
            marginBottom: '48px',
          }}>
            {/* AI Report */}
            <AnimatePresence>
              {aiReport && (
                <div style={{ marginBottom: '48px' }}>
                  <div style={{
                    padding: '32px',
                    borderRadius: '20px',
                    border: `1px solid ${colors.border}`,
                    backgroundColor: colors.surfaceRaised,
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '16px', marginBottom: '16px' }}>
                      <div style={{
                        width: '40px',
                        height: '40px',
                        borderRadius: '10px',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        backgroundColor: 'rgba(16,185,129,0.15)',
                      }}>
                        <Cpu style={{ width: '20px', height: '20px', color: '#10B981' }} />
                      </div>
                      <div>
                        <h3 style={{
                          fontSize: '21px',
                          fontWeight: 600,
                          letterSpacing: '-0.02em',
                          color: colors.text,
                          margin: 0,
                        }}>
                          Analysis Report
                        </h3>
                      </div>
                      <button
                        onClick={() => setShowReport(!showReport)}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '6px',
                          padding: '8px 16px',
                          borderRadius: '14px',
                          border: `1px solid ${colors.border}`,
                          backgroundColor: 'transparent',
                          color: colors.muted,
                          fontSize: '13px',
                          fontWeight: 600,
                          cursor: 'pointer',
                          transition: 'all 150ms ease',
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
                        {showReport ? 'Collapse' : 'Expand'}
                        <ChevronDown style={{
                          width: '14px',
                          height: '14px',
                          transition: 'transform 150ms ease',
                          transform: showReport ? 'rotate(180deg)' : 'rotate(0)',
                        }} />
                      </button>
                    </div>

                    <AnimatePresence>
                      {showReport && (
                        <div style={{
                          padding: '16px',
                          borderRadius: '10px',
                          backgroundColor: '#000000',
                          border: `1px solid ${colors.border}`,
                        }}>
                          <pre style={{
                            whiteSpace: 'pre-wrap',
                            fontSize: '14px',
                            fontFamily: 'JetBrains Mono, Fira Code, monospace',
                            lineHeight: 1.5,
                            color: colors.muted,
                            margin: 0,
                          }}>
                            {aiReport}
                          </pre>
                        </div>
                      )}
                    </AnimatePresence>
                  </div>
                </div>
              )}
            </AnimatePresence>

            {/* Results Grid */}
            {results.length > 0 && (
              <div>
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '12px',
                  marginBottom: '24px',
                }}>
                  <h2 style={{ ...SECTION_HEADING, marginBottom: 0 }}>
                    {results.length} Targets
                  </h2>
                  <span style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '4px',
                    padding: '4px 12px',
                    borderRadius: '999px',
                    backgroundColor: 'rgba(16,185,129,0.1)',
                    color: '#10B981',
                    fontSize: '12px',
                    fontWeight: 600,
                    letterSpacing: '0.05em',
                  }}>
                    <CheckCircle2 style={{ width: '12px', height: '12px' }} />
                    Verified
                  </span>

                  {/* PDF download */}
                  <button
                    onClick={downloadPDF}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                      padding: '8px 16px',
                      borderRadius: '14px',
                      border: `1px solid ${colors.border}`,
                      backgroundColor: 'transparent',
                      color: colors.muted,
                      fontSize: '13px',
                      fontWeight: 600,
                      cursor: 'pointer',
                      transition: 'all 150ms ease',
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
                    <FileDown style={{ width: '14px', height: '14px' }} />
                    PDF Report
                  </button>

                  {/* Clear Results */}
                  <button
                    onClick={clearResults}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                      padding: '8px 16px',
                      borderRadius: '14px',
                      border: `1px solid ${colors.border}`,
                      backgroundColor: 'transparent',
                      color: colors.muted,
                      fontSize: '13px',
                      fontWeight: 600,
                      cursor: 'pointer',
                      transition: 'all 150ms ease',
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.borderColor = 'rgba(239,68,68,0.3)';
                      e.currentTarget.style.color = '#EF4444';
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.borderColor = colors.border;
                      e.currentTarget.style.color = colors.muted;
                    }}
                  >
                    <X style={{ width: '14px', height: '14px' }} />
                    Clear
                  </button>
                </div>

                <div style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(3, 1fr)',
                  gap: '16px',
                }}>
                  {results.map((result) => (
                    <div
                      key={result.ticker}
                      onClick={() => openChart(result.ticker)}
                      style={{
                        padding: '24px',
                        borderRadius: '20px',
                        border: `1px solid ${colors.border}`,
                        backgroundColor: colors.surface,
                        cursor: 'pointer',
                        transition: 'all 150ms ease',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '16px',
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.borderColor = 'rgba(16,185,129,0.4)';
                        e.currentTarget.style.backgroundColor = colors.surfaceRaised;
                        e.currentTarget.style.transform = 'translateY(-2px)';
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.borderColor = colors.border;
                        e.currentTarget.style.backgroundColor = colors.surface;
                        e.currentTarget.style.transform = 'translateY(0)';
                      }}
                    >
                      {/* Header: Ticker + Signal Circle */}
                      <div style={{
                        display: 'flex',
                        alignItems: 'flex-start',
                        justifyContent: 'space-between',
                        width: '100%',
                      }}>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <h3 style={{
                              fontSize: '22px',
                              fontWeight: 600,
                              letterSpacing: '-0.02em',
                              color: colors.text,
                              margin: 0,
                            }}>
                              {result.ticker}
                            </h3>
                            {(() => {
                              const close = result.close;
                              const sma20 = result.sma_20;
                              const ema9 = result.ema_9;
                              let signalColor: string | null = null;
                              if (close && sma20 && ema9) {
                                if (close > sma20 && close > ema9) signalColor = '#10B981';
                                else if (close < sma20 && close < ema9) signalColor = '#EF4444';
                                else signalColor = '#FBBF24';
                              }
                              return signalColor ? (
                                <div style={{
                                  width: '14px',
                                  height: '14px',
                                  borderRadius: '50%',
                                  backgroundColor: signalColor,
                                  boxShadow: `0 0 6px ${signalColor}`,
                                  flexShrink: 0,
                                }} />
                              ) : null;
                            })()}
                          </div>
                          {result.company_name && result.company_name !== result.ticker && (
                            <span style={{
                              fontSize: '13px',
                              fontWeight: 500,
                              color: colors.muted,
                              lineHeight: 1.3,
                              maxWidth: '180px',
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                            }}>
                              {result.company_name}
                            </span>
                          )}
                        </div>
                        {result.sector && result.sector !== 'N/A' && (
                          <span style={{
                            fontSize: '10px',
                            fontWeight: 600,
                            letterSpacing: '0.08em',
                            textTransform: 'uppercase',
                            padding: '3px 10px',
                            borderRadius: '999px',
                            backgroundColor: 'rgba(255,255,255,0.05)',
                            border: `1px solid ${colors.border}`,
                            color: colors.subtle,
                            flexShrink: 0,
                          }}>
                            {result.sector}
                          </span>
                        )}
                      </div>

                      {/* Price */}
                      {result.close && (
                        <div style={{ textAlign: 'center' }}>
                          <p style={{
                            fontSize: '28px',
                            fontWeight: 600,
                            letterSpacing: '-0.02em',
                            fontVariantNumeric: 'tabular-nums',
                            color: colors.text,
                            margin: 0,
                          }}>
                            ${result.close.toFixed(2)}
                          </p>
                          {(result.high_52w || result.low_52w) && (
                            <div style={{ display: 'flex', justifyContent: 'center', gap: '12px', marginTop: '4px' }}>
                              {result.low_52w && (
                                <span style={{ fontSize: '11px', color: colors.subtle }}>
                                  52W Low ${result.low_52w.toFixed(2)}
                                </span>
                              )}
                              {result.high_52w && (
                                <span style={{ fontSize: '11px', color: colors.subtle }}>
                                  52W High ${result.high_52w.toFixed(2)}
                                </span>
                              )}
                            </div>
                          )}
                        </div>
                      )}

                      {/* Signal + Catalyst */}
                      {result.signal && (
                        <span style={{
                          fontSize: '13px',
                          fontWeight: 600,
                          letterSpacing: '0.05em',
                          color: '#10B981',
                          textAlign: 'center',
                        }}>
                          {result.signal}
                        </span>
                      )}

                      {result.fundamental_catalyst && (
                        <div style={{
                          padding: '10px 14px',
                          borderRadius: '10px',
                          backgroundColor: 'rgba(16,185,129,0.04)',
                          border: '1px solid rgba(16,185,129,0.15)',
                          textAlign: 'center',
                        }}>
                          <p style={{
                            fontSize: '13px',
                            lineHeight: 1.4,
                            color: 'rgba(16,185,129,0.9)',
                            margin: 0,
                          }}>
                            {result.fundamental_catalyst}
                          </p>
                        </div>
                      )}

                      {/* Price Stats */}
                      {(result.high_52w || result.low_52w || result.all_time_high || result.all_time_low || result.ath_proximity || result.volume_ratio) && (
                        <div style={{
                          display: 'grid',
                          gridTemplateColumns: 'repeat(2, 1fr)',
                          gap: '8px',
                          paddingTop: '12px',
                          borderTop: `1px solid ${colors.border}`,
                          textAlign: 'center',
                        }}>
                          {result.high_52w !== undefined && (
                            <div>
                              <span style={{ ...LABEL_STYLE, display: 'block', marginBottom: '2px', fontSize: '10px' }}>52W High</span>
                              <span style={{ fontSize: '15px', fontWeight: 600, fontVariantNumeric: 'tabular-nums', color: colors.text }}>
                                ${result.high_52w.toFixed(2)}
                              </span>
                            </div>
                          )}
                          {result.low_52w !== undefined && (
                            <div>
                              <span style={{ ...LABEL_STYLE, display: 'block', marginBottom: '2px', fontSize: '10px' }}>52W Low</span>
                              <span style={{ fontSize: '15px', fontWeight: 600, fontVariantNumeric: 'tabular-nums', color: colors.text }}>
                                ${result.low_52w.toFixed(2)}
                              </span>
                            </div>
                          )}
                          {result.all_time_high !== undefined && (
                            <div>
                              <span style={{ ...LABEL_STYLE, display: 'block', marginBottom: '2px', fontSize: '10px' }}>ATH</span>
                              <span style={{ fontSize: '15px', fontWeight: 600, fontVariantNumeric: 'tabular-nums', color: colors.text }}>
                                ${result.all_time_high.toFixed(2)}
                              </span>
                            </div>
                          )}
                          {result.all_time_low !== undefined && (
                            <div>
                              <span style={{ ...LABEL_STYLE, display: 'block', marginBottom: '2px', fontSize: '10px' }}>ATL</span>
                              <span style={{ fontSize: '15px', fontWeight: 600, fontVariantNumeric: 'tabular-nums', color: colors.text }}>
                                ${result.all_time_low.toFixed(2)}
                              </span>
                            </div>
                          )}
                          {result.ath_proximity != null && (
                            <div>
                              <span style={{ ...LABEL_STYLE, display: 'block', marginBottom: '2px', fontSize: '10px' }}>ATH Proximity</span>
                              <span style={{ fontSize: '15px', fontWeight: 600, fontVariantNumeric: 'tabular-nums', color: '#10B981' }}>
                                {(result.ath_proximity * 100).toFixed(1)}%
                              </span>
                            </div>
                          )}
                          {result.volume_ratio != null && (
                            <div>
                              <span style={{ ...LABEL_STYLE, display: 'block', marginBottom: '2px', fontSize: '10px' }}>Vol Ratio</span>
                              <span style={{ fontSize: '15px', fontWeight: 600, fontVariantNumeric: 'tabular-nums', color: '#3B82F6' }}>
                                {result.volume_ratio.toFixed(2)}x
                              </span>
                            </div>
                          )}
                        </div>
                      )}

                      {/* Volume */}
                      {(result.volume != null || result.volume_ma_50 != null) && (
                        <div style={{
                          display: 'grid',
                          gridTemplateColumns: 'repeat(2, 1fr)',
                          gap: '8px',
                          paddingTop: '12px',
                          borderTop: `1px solid ${colors.border}`,
                          textAlign: 'center',
                        }}>
                          {result.volume != null && (
                            <div>
                              <span style={{ ...LABEL_STYLE, display: 'block', marginBottom: '2px', fontSize: '10px' }}>Volume</span>
                              <span style={{ fontSize: '15px', fontWeight: 600, fontVariantNumeric: 'tabular-nums', color: '#3B82F6' }}>
                                {result.volume.toLocaleString()}
                              </span>
                            </div>
                          )}
                          {result.volume_ma_50 != null && (
                            <div>
                              <span style={{ ...LABEL_STYLE, display: 'block', marginBottom: '2px', fontSize: '10px' }}>Vol MA(50)</span>
                              <span style={{ fontSize: '15px', fontWeight: 600, fontVariantNumeric: 'tabular-nums', color: '#8B5CF6' }}>
                                {Math.round(result.volume_ma_50).toLocaleString()}
                              </span>
                            </div>
                          )}
                        </div>
                      )}

                      {/* Fundamentals */}
                      {(result.eps_growth_qoq !== undefined || result.revenue_growth_qoq !== undefined || result.peg_ratio !== undefined || result.beta !== undefined) && (
                        <div style={{
                          display: 'grid',
                          gridTemplateColumns: 'repeat(2, 1fr)',
                          gap: '8px',
                          paddingTop: '12px',
                          borderTop: `1px solid ${colors.border}`,
                          textAlign: 'center',
                        }}>
                          {result.eps_growth_qoq != null && (
                            <div>
                              <span style={{ ...LABEL_STYLE, display: 'block', marginBottom: '2px', fontSize: '10px' }}>EPS Growth</span>
                              <span style={{ fontSize: '15px', fontWeight: 600, fontVariantNumeric: 'tabular-nums', color: colors.text }}>
                                {result.eps_growth_qoq.toFixed(1)}%
                              </span>
                            </div>
                          )}
                          {result.revenue_growth_qoq != null && (
                            <div>
                              <span style={{ ...LABEL_STYLE, display: 'block', marginBottom: '2px', fontSize: '10px' }}>Rev Growth</span>
                              <span style={{ fontSize: '15px', fontWeight: 600, fontVariantNumeric: 'tabular-nums', color: colors.text }}>
                                {result.revenue_growth_qoq.toFixed(1)}%
                              </span>
                            </div>
                          )}
                          {result.peg_ratio != null && (
                            <div>
                              <span style={{ ...LABEL_STYLE, display: 'block', marginBottom: '2px', fontSize: '10px' }}>PEG</span>
                              <span style={{ fontSize: '15px', fontWeight: 600, fontVariantNumeric: 'tabular-nums', color: colors.text }}>
                                {result.peg_ratio.toFixed(2)}
                              </span>
                            </div>
                          )}
                          {result.beta != null && (
                            <div>
                              <span style={{ ...LABEL_STYLE, display: 'block', marginBottom: '2px', fontSize: '10px' }}>Beta</span>
                              <span style={{ fontSize: '15px', fontWeight: 600, fontVariantNumeric: 'tabular-nums', color: colors.text }}>
                                {result.beta.toFixed(2)}
                              </span>
                            </div>
                          )}
                        </div>
                      )}

                      {/* Technicals */}
                      {(result.sma_20 != null || result.ema_9 != null || result.rsi != null || result.macd != null) && (
                        <div style={{
                          display: 'grid',
                          gridTemplateColumns: 'repeat(2, 1fr)',
                          gap: '8px',
                          paddingTop: '12px',
                          borderTop: `1px solid ${colors.border}`,
                          textAlign: 'center',
                        }}>
                          {result.sma_20 != null && (
                            <div>
                              <span style={{ ...LABEL_STYLE, display: 'block', marginBottom: '2px', fontSize: '10px' }}>SMA(20)</span>
                              <span style={{ fontSize: '15px', fontWeight: 600, fontVariantNumeric: 'tabular-nums', color: colors.text }}>
                                {result.sma_20.toFixed(2)}
                              </span>
                            </div>
                          )}
                          {result.ema_9 != null && (
                            <div>
                              <span style={{ ...LABEL_STYLE, display: 'block', marginBottom: '2px', fontSize: '10px' }}>EMA(9)</span>
                              <span style={{ fontSize: '15px', fontWeight: 600, fontVariantNumeric: 'tabular-nums', color: colors.text }}>
                                {result.ema_9.toFixed(2)}
                              </span>
                            </div>
                          )}
                          {result.rsi != null && (
                            <div>
                              <span style={{ ...LABEL_STYLE, display: 'block', marginBottom: '2px', fontSize: '10px' }}>RSI(14)</span>
                              <span style={{ fontSize: '15px', fontWeight: 600, fontVariantNumeric: 'tabular-nums', color: colors.text }}>
                                {result.rsi.toFixed(1)}
                              </span>
                            </div>
                          )}
                          {result.macd != null && (
                            <div>
                              <span style={{ ...LABEL_STYLE, display: 'block', marginBottom: '2px', fontSize: '10px' }}>MACD</span>
                              <span style={{ fontSize: '15px', fontWeight: 600, fontVariantNumeric: 'tabular-nums', color: colors.text }}>
                                {result.macd.toFixed(3)}
                              </span>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* === EMPTY STATE === */}
        {!isScanning && results.length === 0 && !error && (
          <div style={{
            textAlign: 'center',
            paddingTop: '96px',
            paddingBottom: '96px',
          }}>
            <div style={{
              width: '48px',
              height: '48px',
              borderRadius: '14px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              backgroundColor: 'rgba(255,255,255,0.05)',
              border: `1px solid ${colors.border}`,
              margin: '0 auto 16px',
            }}>
              <Sparkles style={{ width: '20px', height: '20px', color: colors.subtle }} />
            </div>
            <p style={{
              fontSize: '17px',
              fontWeight: 600,
              letterSpacing: '-0.022em',
              color: colors.muted,
              margin: 0,
            }}>
              Select a mode and start a scan
            </p>
            <p style={{
              ...BODY_TEXT,
              fontSize: '14px',
              color: colors.subtle,
              marginTop: '4px',
            }}>
              Press <kbd style={{ padding: '2px 6px', borderRadius: '4px', backgroundColor: 'rgba(255,255,255,0.08)', fontFamily: 'JetBrains Mono, monospace', fontSize: '12px' }}>S</kbd> to start
            </p>
          </div>
        )}

        {/* === FOOTER === */}
        <div style={{
          padding: '16px 0',
          borderTop: `1px solid ${colors.border}`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '24px',
          marginBottom: '16px',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={LABEL_STYLE}>System</span>
            <span style={{
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
              padding: '3px 10px',
              borderRadius: '999px',
              backgroundColor: 'rgba(16,185,129,0.1)',
              color: '#34D399',
              fontSize: '11px',
              fontWeight: 600,
              letterSpacing: '0.05em',
            }}>
              <span style={{ width: '5px', height: '5px', borderRadius: '50%', backgroundColor: '#10B981' }} />
              Ready
            </span>
          </div>
          <span style={{
            ...LABEL_STYLE,
            fontSize: '11px',
            fontVariantNumeric: 'tabular-nums',
          }}>
            {lastUpdated}
          </span>
        </div>
      </div>

      {/* Error Toast */}
      <AnimatePresence>
        {error && (
          <div
            style={{
              position: 'fixed',
              bottom: '24px',
              left: '50%',
              transform: 'translateX(-50%)',
              zIndex: 50,
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              padding: '12px 20px',
              borderRadius: '14px',
              backgroundColor: 'rgba(239,68,68,0.1)',
              border: '1px solid rgba(239,68,68,0.2)',
            }}
          >
            <AlertCircle style={{ width: '18px', height: '18px', color: '#EF4444' }} />
            <span style={{ fontSize: '15px', fontWeight: 600, color: '#EF4444' }}>{error}</span>
          </div>
        )}
      </AnimatePresence>

      {/* Candlestick Chart Modal */}
      {chartTicker && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 100,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            backgroundColor: 'rgba(0,0,0,0.7)',
            backdropFilter: 'blur(8px)',
          }}
          onClick={(e) => {
            if (e.target === e.currentTarget) closeChart();
          }}
        >
          <div
            style={{
              width: '90%',
              maxWidth: '960px',
              maxHeight: '85vh',
              borderRadius: '20px',
              backgroundColor: colors.surface,
              border: `1px solid ${colors.border}`,
              display: 'flex',
              flexDirection: 'column',
              overflow: 'hidden',
            }}
          >
            {/* Modal Header */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '20px 24px',
                borderBottom: `1px solid ${colors.border}`,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <div
                  style={{
                    width: '36px',
                    height: '36px',
                    borderRadius: '10px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    backgroundColor: 'rgba(16,185,129,0.15)',
                  }}
                >
                  <BarChart3 style={{ width: '18px', height: '18px', color: '#10B981' }} />
                </div>
                <div>
                  <h3
                    style={{
                      fontSize: '20px',
                      fontWeight: 600,
                      letterSpacing: '-0.02em',
                      color: colors.text,
                      margin: 0,
                    }}
                  >
                    {chartTicker}
                  </h3>
                  <span style={{ ...LABEL_STYLE, fontSize: '11px' }}>
                    Candlestick Chart
                  </span>
                </div>
              </div>
              <button
                onClick={closeChart}
                style={{
                  width: '32px',
                  height: '32px',
                  borderRadius: '8px',
                  border: `1px solid ${colors.border}`,
                  backgroundColor: 'transparent',
                  color: colors.muted,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  cursor: 'pointer',
                  transition: 'all 150ms ease',
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
                <X style={{ width: '16px', height: '16px' }} />
              </button>
            </div>

            {/* Chart Body */}
            <div style={{ flex: 1, padding: '16px 24px 24px', minHeight: '400px' }}>
              {chartLoading ? (
                <div
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    justifyContent: 'center',
                    height: '400px',
                    gap: '12px',
                  }}
                >
                  <Loader2 style={{ width: '24px', height: '24px', color: colors.muted }} className="animate-spin" />
                  <span style={{ ...LABEL_STYLE, fontSize: '13px' }}>
                    Loading chart data...
                  </span>
                </div>
              ) : chartData.length > 0 ? (
                <CandleStickChart data={chartData} height={420} indicators={chartIndicators} />
              ) : (
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    height: '400px',
                    color: colors.subtle,
                    fontSize: '15px',
                  }}
                >
                  No chart data available
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
