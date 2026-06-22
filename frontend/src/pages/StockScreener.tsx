import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
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
  ArrowRight,
} from "lucide-react";
import { AnimatePresence } from "framer-motion";
import { useTheme } from "../context/ThemeContext";
import { recordAppReferrer } from "../components/layout/Layout";
import TerminalLog from "../components/screener/TerminalLog";
import ChartModal from "../components/screener/ChartModal";

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
  score?: number;
  trend_score?: number;
  momentum_score?: number;
  volatility_score?: number;
  volume_score?: number;
  mfi?: number;
  volume_cluster_days?: number;
  rs_ratio?: number;
  bandwidth_pct?: number;
  next_earnings_date?: string;
  days_until_earnings?: number;
  eps_estimate?: number;
  time_of_day?: string;
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
  fontSize: "28px",
  fontWeight: 600,
  letterSpacing: "-0.02em",
  lineHeight: 1.14,
  color: "#FAFAFA",
};

const BODY_TEXT: React.CSSProperties = {
  fontSize: "17px",
  fontWeight: 400,
  lineHeight: 1.47,
  letterSpacing: "-0.022em",
  color: "rgba(255,255,255,0.7)",
};

const LABEL_STYLE: React.CSSProperties = {
  fontSize: "12px",
  fontWeight: 600,
  letterSpacing: "0.15em",
  textTransform: "uppercase",
  color: "rgba(255,255,255,0.4)",
};

const SCREENER_STATE_KEY = "screener:lastScan";

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
  const [scanCompleted, setScanCompleted] = useState(false);
  const [showHelp, setShowHelp] = useState(false);
  const [showQuantHelp, setShowQuantHelp] = useState(false);
  const [showIndicatorHelp, setShowIndicatorHelp] = useState(false);
  const [filters, setFilters] = useState({
    consolidation_days: 15,
    mfi_threshold: 55,
    volume_cluster_days: 3,
    rs_minimum: 0.8,
    use_sector_momentum: true,
  });
  const [quantFilters, setQuantFilters] = useState<Record<string, any> | null>(
    null,
  );
  const [isParsingFilters, setIsParsingFilters] = useState(false);
  const [lastUpdated] = useState<string>(new Date().toLocaleTimeString());
  const [baseWeight, setBaseWeight] = useState<number>(60);
  const navigate = useNavigate();

  // Chart modal state
  const [chartTicker, setChartTicker] = useState<string | null>(null);

  const colors = {
    text: isDarkMode ? "#FAFAFA" : "#1d1d1f",
    muted: isDarkMode ? "rgba(255,255,255,0.7)" : "rgba(0,0,0,0.8)",
    subtle: isDarkMode ? "rgba(255,255,255,0.4)" : "rgba(0,0,0,0.48)",
    border: isDarkMode ? "rgba(255,255,255,0.08)" : "rgba(0,0,0,0.04)",
    borderHover: isDarkMode ? "rgba(255,255,255,0.15)" : "rgba(0,0,0,0.1)",
    surface: isDarkMode ? "#0a0a0a" : "#ffffff",
    surfaceRaised: isDarkMode ? "#111111" : "#fafafc",
    inputBg: isDarkMode ? "#000000" : "#ffffff",
    canvas: isDarkMode ? "#050505" : "#f5f5f7",
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
        const isFresh =
          state.timestamp && Date.now() - state.timestamp < 24 * 60 * 60 * 1000;
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
    } catch {
      /* ignore */
    }
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
      try {
        localStorage.setItem(SCREENER_STATE_KEY, JSON.stringify(state));
      } catch {
        /* ignore */
      }
    }
  }, [results, scanStatus, aiReport, logs, progress, selectedMode, useAi]);

  // Keyboard shortcut: s to start scan
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (
        (e.key === "s" && !isScanning && !e.target) ||
        ((e.target as HTMLElement).tagName !== "INPUT" &&
          (e.target as HTMLElement).tagName !== "TEXTAREA")
      ) {
        if (!isScanning) startScan();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isScanning, selectedMode, useAi, customPrompt, filters]);

  const clearResults = () => {
    setResults([]);
    setScanStatus(null);
    setAiReport(null);
    setLogs([]);
    setProgress(0);
    setShowReport(false);
    setQuantFilters(null);
    try {
      localStorage.removeItem(SCREENER_STATE_KEY);
    } catch {
      /* ignore */
    }
  };

  const exportToQuantGen = () => {
    const tickers = results.map((r) => r.ticker).join(",");
    const fromDate = cutoffDate || new Date().toISOString().split("T")[0];
    recordAppReferrer('/screener', 'AI Stock Screener');
    navigate(
      `/quantgen/build?tickers=${encodeURIComponent(tickers)}&from_date=${fromDate}`,
    );
  };

  // Clear quant filters when switching away from quant_strategy mode
  useEffect(() => {
    if (selectedMode !== "quant_strategy") {
      setQuantFilters(null);
    }
  }, [selectedMode]);

  const openChart = async (ticker: string) => {
    setChartTicker(ticker);
    try {
      const res = await fetch(`/api/ohlcv/${ticker.toLowerCase()}`);
      await res.json();
    } catch (err) {
      console.error("Failed to fetch chart data:", err);
    } finally {
    }
  };

  const closeChart = () => {
    setChartTicker(null);
  };


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
    setScanCompleted(false);

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
          filters:
            selectedMode === "dormant_giant"
              ? filters
              : quantFilters || undefined,
          base_weight:
            selectedMode === "quant_strategy" ? baseWeight : undefined,
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
              prev ? { ...prev, progress: eventData.progress } : null,
            );
          } else if (type === "log") {
            setLogs((prev) => [...prev, eventData]);
          } else if (type === "status") {
            setScanStatus((prev) =>
              prev
                ? {
                    ...prev,
                    status: eventData.status,
                    progress: eventData.progress ?? prev.progress,
                  }
                : null,
            );
            if (eventData.status === "completed") {
              setIsScanning(false);
              setProgress(100);
              setScanCompleted(true);
              fetchResults(scanId);
              eventSource.close();
            } else if (eventData.status === "failed") {
              setIsScanning(false);
              setScanCompleted(true);
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
            const newLogs = data.logs.filter(
              (l: LogEntry) => !existingKeys.has(l.message),
            );
            return [...prev, ...newLogs];
          });
        }

        if (data.status === "running") {
          setTimeout(poll, 1000);
        } else if (data.status === "completed") {
          setIsScanning(false);
          setProgress(100);
          setScanCompleted(true);
          fetchResults(id);
        } else if (data.status === "failed") {
          setIsScanning(false);
          setScanCompleted(true);
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

  const ScoreBadge = ({ score }: { score: number }) => {
    const color = score >= 70 ? "#10B981" : score >= 50 ? "#F59E0B" : "#EF4444";
    const label = score >= 70 ? "Strong" : score >= 50 ? "Moderate" : "Weak";
    return (
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "8px",
        }}
      >
        <div
          style={{
            width: "40px",
            height: "40px",
            borderRadius: "10px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            backgroundColor: `${color}15`,
            border: `1px solid ${color}30`,
          }}
        >
          <span style={{ fontSize: "15px", fontWeight: 700, color }}>
            {score.toFixed(0)}
          </span>
        </div>
        <div>
          <div
            style={{ fontSize: "12px", fontWeight: 600, color: colors.muted }}
          >
            Explosiveness
          </div>
          <div style={{ fontSize: "13px", fontWeight: 600, color }}>
            {label}
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="min-h-screen" style={{ backgroundColor: colors.canvas }}>
      <div style={{ maxWidth: "1280px", padding: "0 32px", margin: "0 auto" }}>
        {/* === HEADER === */}
        <div
          style={{
            paddingTop: "64px",
            paddingBottom: "48px",
            textAlign: "center",
          }}
        >
          <h1
            style={{
              fontSize: "32px",
              fontWeight: 600,
              letterSpacing: "-0.02em",
              lineHeight: 1.14,
              color: colors.text,
              marginBottom: "8px",
            }}
          >
            AI Stock Screener
          </h1>
          <p style={{ ...BODY_TEXT, maxWidth: "600px", margin: "0 auto" }}>
            Multi-agent technical and fundamental screening powered by
            intelligent agents
          </p>
        </div>

        {/* === MODE SELECTION === */}
        <section style={{ marginBottom: "48px" }}>
          <h2
            style={{
              ...SECTION_HEADING,
              marginBottom: "24px",
              textAlign: "center",
            }}
          >
            Select Mode
          </h2>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(2, 1fr)",
              gap: "24px",
            }}
          >
            {modes.map((mode) => {
              const isSelected = selectedMode === mode.id;
              const Icon = mode.id === "dormant_giant" ? Zap : BarChart3;

              return (
                <div
                  key={mode.id}
                  onClick={() => setSelectedMode(mode.id)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ")
                      setSelectedMode(mode.id);
                  }}
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    textAlign: "center",
                    padding: "32px",
                    borderRadius: "20px",
                    backgroundColor: isSelected
                      ? colors.surfaceRaised
                      : "transparent",
                    border: `1px solid ${isSelected ? "rgba(16,185,129,0.5)" : colors.border}`,
                    cursor: "pointer",
                    transition: "all 150ms ease",
                    position: "relative",
                    gap: "16px",
                    outline: "none",
                  }}
                  onMouseEnter={(e) => {
                    if (!isSelected) {
                      e.currentTarget.style.backgroundColor = colors.surface;
                      e.currentTarget.style.borderColor = colors.borderHover;
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (!isSelected) {
                      e.currentTarget.style.backgroundColor = "transparent";
                      e.currentTarget.style.borderColor = colors.border;
                    }
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      alignItems: "center",
                      gap: "12px",
                      width: "100%",
                    }}
                  >
                    <div
                      style={{
                        width: "40px",
                        height: "40px",
                        borderRadius: "10px",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        backgroundColor: isSelected
                          ? "rgba(16,185,129,0.15)"
                          : "rgba(255,255,255,0.05)",
                        transition: "background-color 150ms ease",
                      }}
                    >
                      <Icon
                        style={{
                          width: "20px",
                          height: "20px",
                          color: isSelected
                            ? "#10B981"
                            : "rgba(255,255,255,0.4)",
                        }}
                      />
                    </div>
                    <h3
                      style={{
                        fontSize: "21px",
                        fontWeight: 600,
                        letterSpacing: "-0.02em",
                        color: isSelected ? colors.text : colors.subtle,
                        transition: "color 150ms ease",
                      }}
                    >
                      {mode.name}
                    </h3>
                  </div>

                  <p
                    style={{
                      ...BODY_TEXT,
                      fontSize: "15px",
                      color: isSelected ? colors.muted : colors.subtle,
                      margin: 0,
                      textAlign: "center",
                    }}
                  >
                    {mode.description}
                  </p>

                  {mode.agents.length > 0 && (
                    <div
                      style={{
                        display: "flex",
                        flexWrap: "wrap",
                        gap: "6px",
                        marginTop: "8px",
                        justifyContent: "center",
                      }}
                    >
                      {mode.agents.slice(0, 4).map((agent) => (
                        <span
                          key={agent}
                          style={{
                            fontSize: "11px",
                            fontWeight: 600,
                            letterSpacing: "0.05em",
                            padding: "4px 12px",
                            borderRadius: "999px",
                            backgroundColor: isSelected
                              ? "rgba(16,185,129,0.1)"
                              : "rgba(255,255,255,0.04)",
                            color: isSelected ? "#10B981" : colors.subtle,
                            border: `1px solid ${isSelected ? "rgba(16,185,129,0.2)" : "transparent"}`,
                          }}
                        >
                          {agent}
                        </span>
                      ))}
                    </div>
                  )}
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      if (mode.id === "dormant_giant") setShowHelp(true);
                      else setShowQuantHelp(true);
                    }}
                    style={{
                      marginTop: "4px",
                      display: "flex",
                      alignItems: "center",
                      gap: "6px",
                      padding: "6px 14px",
                      borderRadius: "8px",
                      border: `1px solid ${colors.border}`,
                      backgroundColor: "transparent",
                      color: colors.muted,
                      fontSize: "12px",
                      fontWeight: 600,
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
                    <span>How it works</span>
                  </button>

                  {mode.id === "quant_strategy" && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setShowIndicatorHelp(true);
                      }}
                      style={{
                        marginTop: "8px",
                        display: "flex",
                        alignItems: "center",
                        gap: "6px",
                        padding: "6px 14px",
                        borderRadius: "8px",
                        border: "1px solid #3B82F6",
                        backgroundColor: "rgba(59, 130, 246, 0.1)",
                        color: "#3B82F6",
                        fontSize: "12px",
                        fontWeight: 600,
                        cursor: "pointer",
                        transition: "all 150ms ease",
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.backgroundColor =
                          "rgba(59, 130, 246, 0.2)";
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.backgroundColor =
                          "rgba(59, 130, 246, 0.1)";
                      }}
                    >
                      <Zap style={{ width: "14px", height: "14px" }} />
                      <span>Indicator Help</span>
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        </section>

        {/* === CONFIGURATION === */}
        <section style={{ marginBottom: "48px" }}>
          <h2
            style={{
              ...SECTION_HEADING,
              marginBottom: "24px",
              textAlign: "center",
            }}
          >
            Configuration
          </h2>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(2, 1fr)",
              gap: "24px",
            }}
          >
            {/* AI Analysis */}
            <div
              style={{
                padding: "32px",
                borderRadius: "20px",
                border: `1px solid ${colors.border}`,
                backgroundColor: colors.surface,
              }}
            >
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  gap: "12px",
                  marginBottom: "20px",
                }}
              >
                <div
                  style={{
                    width: "36px",
                    height: "36px",
                    borderRadius: "10px",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    backgroundColor: useAi
                      ? "rgba(16,185,129,0.15)"
                      : "rgba(255,255,255,0.05)",
                  }}
                >
                  <Cpu
                    style={{
                      width: "18px",
                      height: "18px",
                      color: useAi ? "#10B981" : colors.subtle,
                    }}
                  />
                </div>
                <div style={{ textAlign: "center" }}>
                  <span
                    style={{
                      fontSize: "17px",
                      fontWeight: 600,
                      letterSpacing: "-0.022em",
                      color: colors.text,
                    }}
                  >
                    AI Analysis
                  </span>
                  <span
                    style={{
                      ...LABEL_STYLE,
                      display: "block",
                      marginTop: "2px",
                    }}
                  >
                    {useAi ? "Enabled" : "Disabled"}
                  </span>
                </div>
                <button
                  onClick={() => setUseAi(!useAi)}
                  style={{
                    width: "44px",
                    height: "24px",
                    borderRadius: "12px",
                    border: "none",
                    backgroundColor: useAi
                      ? "#10B981"
                      : "rgba(255,255,255,0.15)",
                    cursor: "pointer",
                    position: "relative",
                    transition: "background-color 150ms ease",
                    flexShrink: 0,
                  }}
                  aria-label={`Toggle AI analysis ${useAi ? "off" : "on"}`}
                >
                  <div
                    style={{
                      position: "absolute",
                      top: "2px",
                      width: "20px",
                      height: "20px",
                      borderRadius: "50%",
                      backgroundColor: "#fff",
                      transition: "transform 150ms ease",
                      transform: useAi ? "translateX(20px)" : "translateX(2px)",
                      boxShadow: "0 1px 3px rgba(0,0,0,0.3)",
                    }}
                  />
                </button>
              </div>

              <div style={{ textAlign: "center", marginBottom: "20px" }}>
                <label
                  style={{
                    ...LABEL_STYLE,
                    display: "block",
                    marginBottom: "8px",
                  }}
                >
                  Cutoff Date
                </label>
                <input
                  type="date"
                  value={cutoffDate}
                  onChange={(e) => setCutoffDate(e.target.value)}
                  max={new Date().toISOString().split("T")[0]}
                  style={{
                    width: "100%",
                    padding: "10px 14px",
                    borderRadius: "10px",
                    border: `1px solid ${colors.border}`,
                    backgroundColor: colors.inputBg,
                    color: colors.text,
                    fontSize: "14px",
                    outline: "none",
                    transition: "border-color 150ms ease",
                  }}
                  onFocus={(e) =>
                    (e.currentTarget.style.borderColor = "rgba(16,185,129,0.5)")
                  }
                  onBlur={(e) =>
                    (e.currentTarget.style.borderColor = colors.border)
                  }
                />
                <span
                  style={{ ...LABEL_STYLE, display: "block", marginTop: "4px" }}
                >
                  {cutoffDate
                    ? "Screen as of this date"
                    : "Leave blank for latest data"}
                </span>
              </div>

              <div style={{ textAlign: "center" }}>
                <label
                  style={{
                    ...LABEL_STYLE,
                    display: "block",
                    marginBottom: "8px",
                  }}
                >
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
                    width: "100%",
                    height: "120px",
                    padding: "16px",
                    borderRadius: "14px",
                    border: `1px solid ${colors.border}`,
                    backgroundColor: colors.inputBg,
                    color: colors.text,
                    fontSize: "14px",
                    fontFamily: "JetBrains Mono, Fira Code, monospace",
                    lineHeight: 1.5,
                    resize: "vertical",
                    outline: "none",
                    transition: "border-color 150ms ease",
                  }}
                  onFocus={(e) =>
                    (e.currentTarget.style.borderColor = "rgba(16,185,129,0.5)")
                  }
                  onBlur={(e) =>
                    (e.currentTarget.style.borderColor = colors.border)
                  }
                />

                {/* Generate Filters button for Quant Strategy */}
                {selectedMode === "quant_strategy" && (
                  <button
                    onClick={generateFilters}
                    disabled={isParsingFilters || !customPrompt.trim()}
                    style={{
                      marginTop: "12px",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      gap: "8px",
                      width: "100%",
                      padding: "10px 0",
                      borderRadius: "10px",
                      border: "none",
                      backgroundColor: isParsingFilters
                        ? colors.subtle
                        : "#3B82F6",
                      color: "#fff",
                      fontSize: "14px",
                      fontWeight: 600,
                      cursor:
                        isParsingFilters || !customPrompt.trim()
                          ? "not-allowed"
                          : "pointer",
                      opacity:
                        isParsingFilters || !customPrompt.trim() ? 0.5 : 1,
                      transition: "all 150ms ease",
                    }}
                  >
                    {isParsingFilters ? (
                      <>
                        <Loader2
                          style={{
                            width: "16px",
                            height: "16px",
                            animation: "spin 1s linear infinite",
                          }}
                        />
                        Parsing Filters...
                      </>
                    ) : (
                      <>
                        <Sparkles style={{ width: "16px", height: "16px" }} />
                        Generate Filters from Prompt
                      </>
                    )}
                  </button>
                )}

                {/* Filter Review Panel */}
                {selectedMode === "quant_strategy" && quantFilters && (
                  <div
                    style={{
                      marginTop: "16px",
                      padding: "20px",
                      borderRadius: "14px",
                      border: `1px solid ${colors.border}`,
                      backgroundColor: colors.inputBg,
                      textAlign: "left",
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        marginBottom: "12px",
                      }}
                    >
                      <span style={{ ...LABEL_STYLE, fontSize: "11px" }}>
                        Parsed Filters — Edit before scanning
                      </span>
                      <span
                        style={{
                          fontSize: "11px",
                          color: colors.subtle,
                          display: "block",
                          marginBottom: "8px",
                          marginTop: "-6px",
                        }}
                      >
                        Earnings filter only applies to stocks with cached calendar data.
                      </span>
                      <button
                        onClick={() => setQuantFilters(null)}
                        style={{
                          background: "none",
                          border: "none",
                          color: colors.subtle,
                          fontSize: "12px",
                          cursor: "pointer",
                        }}
                      >
                        Clear
                      </button>
                    </div>

                    {/* ATH Proximity */}
                    <div style={{ marginBottom: "12px" }}>
                      <div
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          marginBottom: "4px",
                        }}
                      >
                        <span style={{ fontSize: "13px", color: colors.muted }}>
                          ATH Proximity Min
                        </span>
                        <span
                          style={{
                            fontSize: "13px",
                            fontWeight: 600,
                            color: "#10B981",
                          }}
                        >
                          {quantFilters.ath_proximity_min != null
                            ? quantFilters.ath_proximity_min.toFixed(2)
                            : "Any"}
                        </span>
                      </div>
                      <input
                        type="range"
                        min={0.5}
                        max={1.0}
                        step={0.01}
                        value={quantFilters.ath_proximity_min ?? 0.5}
                        onChange={(e) =>
                          setQuantFilters({
                            ...quantFilters,
                            ath_proximity_min: parseFloat(e.target.value),
                          })
                        }
                        style={{
                          width: "100%",
                          height: "4px",
                          appearance: "none",
                          backgroundColor: "rgba(255,255,255,0.1)",
                          borderRadius: "2px",
                        }}
                      />
                    </div>

                    {/* Volume Ratio */}
                    <div style={{ marginBottom: "12px" }}>
                      <div
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          marginBottom: "4px",
                        }}
                      >
                        <span style={{ fontSize: "13px", color: colors.muted }}>
                          Volume Ratio Min
                        </span>
                        <span
                          style={{
                            fontSize: "13px",
                            fontWeight: 600,
                            color: "#10B981",
                          }}
                        >
                          {quantFilters.volume_ratio_min != null
                            ? quantFilters.volume_ratio_min.toFixed(2)
                            : "Any"}
                        </span>
                      </div>
                      <input
                        type="range"
                        min={0.5}
                        max={5.0}
                        step={0.1}
                        value={quantFilters.volume_ratio_min ?? 0.5}
                        onChange={(e) =>
                          setQuantFilters({
                            ...quantFilters,
                            volume_ratio_min: parseFloat(e.target.value),
                          })
                        }
                        style={{
                          width: "100%",
                          height: "4px",
                          appearance: "none",
                          backgroundColor: "rgba(255,255,255,0.1)",
                          borderRadius: "2px",
                        }}
                      />
                    </div>

                    {/* Dynamic Indicator Filters */}
                    {(quantFilters.indicator_filters?.length > 0 || true) && (
                      <div style={{ marginBottom: "12px" }}>
                        <div
                          style={{
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "space-between",
                            marginBottom: "8px",
                          }}
                        >
                          <span
                            style={{
                              fontSize: "13px",
                              fontWeight: 600,
                              color: colors.text,
                            }}
                          >
                            Indicator Filters
                          </span>
                          <button
                            onClick={() => {
                              const current =
                                quantFilters.indicator_filters || [];
                              setQuantFilters({
                                ...quantFilters,
                                indicator_filters: [
                                  ...current,
                                  { column: "momentum_rsi", min: 0, max: 100 },
                                ],
                              });
                            }}
                            style={{
                              background: "none",
                              border: `1px solid ${colors.border}`,
                              borderRadius: "6px",
                              color: "#10B981",
                              fontSize: "12px",
                              padding: "4px 10px",
                              cursor: "pointer",
                            }}
                          >
                            + Add Filter
                          </button>
                        </div>
                        {(quantFilters.indicator_filters || []).map(
                          (item: any, idx: number) => (
                            <div
                              key={idx}
                              style={{
                                marginBottom: "8px",
                                padding: "10px",
                                borderRadius: "10px",
                                border: `1px solid ${colors.border}`,
                                backgroundColor: colors.surface,
                              }}
                            >
                              <div
                                style={{
                                  display: "flex",
                                  alignItems: "center",
                                  gap: "8px",
                                  marginBottom: "8px",
                                  flexWrap: "wrap",
                                }}
                              >
                                <input
                                  type="text"
                                  value={item.column || ""}
                                  placeholder="Indicator column"
                                  onChange={(e) => {
                                    const updated = [
                                      ...(quantFilters.indicator_filters || []),
                                    ];
                                    updated[idx] = {
                                      ...item,
                                      column: e.target.value,
                                    };
                                    setQuantFilters({
                                      ...quantFilters,
                                      indicator_filters: updated,
                                    });
                                  }}
                                  style={{
                                    flex: 1,
                                    minWidth: "120px",
                                    padding: "6px 8px",
                                    borderRadius: "6px",
                                    border: `1px solid ${colors.border}`,
                                    backgroundColor: colors.inputBg,
                                    color: colors.text,
                                    fontSize: "13px",
                                  }}
                                />
                                {/* Cross-indicator condition selector */}
                                <select
                                  value={item.condition || ""}
                                  onChange={(e) => {
                                    const updated = [
                                      ...(quantFilters.indicator_filters || []),
                                    ];
                                    const condition =
                                      e.target.value || undefined;
                                    updated[idx] = { ...item, condition };
                                    if (!condition) {
                                      delete updated[idx].reference_column;
                                      delete updated[idx].reference_params;
                                      delete updated[idx].tolerance;
                                    } else if (condition !== "equals") {
                                      delete updated[idx].tolerance;
                                    } else if (
                                      condition === "equals" &&
                                      item.tolerance === undefined
                                    ) {
                                      updated[idx].tolerance = 0.01;
                                    }
                                    setQuantFilters({
                                      ...quantFilters,
                                      indicator_filters: updated,
                                    });
                                  }}
                                  style={{
                                    padding: "6px 8px",
                                    borderRadius: "6px",
                                    border: `1px solid ${colors.border}`,
                                    backgroundColor: colors.inputBg,
                                    color: colors.text,
                                    fontSize: "13px",
                                  }}
                                >
                                  <option value="">Threshold</option>
                                  <option value="above">Above</option>
                                  <option value="below">Below</option>
                                  <option value="equals">Equals</option>
                                </select>
                                {item.condition && (
                                  <>
                                    <input
                                      type="text"
                                      value={item.reference_column || ""}
                                      placeholder="Reference indicator"
                                      onChange={(e) => {
                                        const updated = [
                                          ...(quantFilters.indicator_filters ||
                                            []),
                                        ];
                                        updated[idx] = {
                                          ...item,
                                          reference_column:
                                            e.target.value || undefined,
                                        };
                                        setQuantFilters({
                                          ...quantFilters,
                                          indicator_filters: updated,
                                        });
                                      }}
                                      style={{
                                        flex: 1,
                                        minWidth: "120px",
                                        padding: "6px 8px",
                                        borderRadius: "6px",
                                        border: `1px solid ${colors.border}`,
                                        backgroundColor: colors.inputBg,
                                        color: colors.text,
                                        fontSize: "13px",
                                      }}
                                    />
                                    {item.condition === "equals" && (
                                      <div
                                        style={{
                                          display: "flex",
                                          alignItems: "center",
                                          gap: "4px",
                                        }}
                                      >
                                        <span
                                          style={{
                                            fontSize: "11px",
                                            color: colors.subtle,
                                          }}
                                        >
                                          Tol:
                                        </span>
                                        <input
                                          type="number"
                                          step="0.001"
                                          min="0"
                                          value={item.tolerance ?? 0.01}
                                          onChange={(e) => {
                                            const updated = [
                                              ...(quantFilters.indicator_filters ||
                                                []),
                                            ];
                                            updated[idx] = {
                                              ...item,
                                              tolerance: e.target.value
                                                ? parseFloat(e.target.value)
                                                : 0,
                                            };
                                            setQuantFilters({
                                              ...quantFilters,
                                              indicator_filters: updated,
                                            });
                                          }}
                                          style={{
                                            width: "70px",
                                            padding: "6px 8px",
                                            borderRadius: "6px",
                                            border: `1px solid ${colors.border}`,
                                            backgroundColor: colors.inputBg,
                                            color: colors.text,
                                            fontSize: "13px",
                                          }}
                                        />
                                      </div>
                                    )}
                                  </>
                                )}
                                <button
                                  onClick={() => {
                                    const updated = (
                                      quantFilters.indicator_filters || []
                                    ).filter((_: any, i: number) => i !== idx);
                                    setQuantFilters({
                                      ...quantFilters,
                                      indicator_filters: updated,
                                    });
                                  }}
                                  style={{
                                    background: "none",
                                    border: "none",
                                    color: "#f43f5e",
                                    fontSize: "16px",
                                    cursor: "pointer",
                                    padding: "0 4px",
                                  }}
                                >
                                  ×
                                </button>
                              </div>
                              {/* Min/Max inputs for threshold-based filters */}
                              {!item.condition && (
                                <div
                                  style={{
                                    display: "grid",
                                    gridTemplateColumns: "1fr 1fr",
                                    gap: "8px",
                                  }}
                                >
                                  <input
                                    type="number"
                                    value={item.min ?? ""}
                                    placeholder="Min"
                                    onChange={(e) => {
                                      const updated = [
                                        ...(quantFilters.indicator_filters ||
                                          []),
                                      ];
                                      updated[idx] = {
                                        ...item,
                                        min: e.target.value
                                          ? parseFloat(e.target.value)
                                          : undefined,
                                      };
                                      setQuantFilters({
                                        ...quantFilters,
                                        indicator_filters: updated,
                                      });
                                    }}
                                    style={{
                                      width: "100%",
                                      padding: "6px 8px",
                                      borderRadius: "6px",
                                      border: `1px solid ${colors.border}`,
                                      backgroundColor: colors.inputBg,
                                      color: colors.text,
                                      fontSize: "13px",
                                    }}
                                  />
                                  <input
                                    type="number"
                                    value={item.max ?? ""}
                                    placeholder="Max"
                                    onChange={(e) => {
                                      const updated = [
                                        ...(quantFilters.indicator_filters ||
                                          []),
                                      ];
                                      updated[idx] = {
                                        ...item,
                                        max: e.target.value
                                          ? parseFloat(e.target.value)
                                          : undefined,
                                      };
                                      setQuantFilters({
                                        ...quantFilters,
                                        indicator_filters: updated,
                                      });
                                    }}
                                    style={{
                                      width: "100%",
                                      padding: "6px 8px",
                                      borderRadius: "6px",
                                      border: `1px solid ${colors.border}`,
                                      backgroundColor: colors.inputBg,
                                      color: colors.text,
                                      fontSize: "13px",
                                    }}
                                  />
                                </div>
                              )}
                            </div>
                          ),
                        )}
                      </div>
                    )}

                    {/* Sort By & Order */}
                    <div
                      style={{
                        display: "grid",
                        gridTemplateColumns: "2fr 1fr",
                        gap: "12px",
                        marginBottom: "12px",
                      }}
                    >
                      <div>
                        <span
                          style={{
                            fontSize: "13px",
                            color: colors.muted,
                            display: "block",
                            marginBottom: "4px",
                          }}
                        >
                          Sort By
                        </span>
                        <select
                          value={quantFilters.sort_by || "ticker"}
                          onChange={(e) =>
                            setQuantFilters({
                              ...quantFilters,
                              sort_by: e.target.value,
                            })
                          }
                          style={{
                            width: "100%",
                            padding: "8px 10px",
                            borderRadius: "8px",
                            border: `1px solid ${colors.border}`,
                            backgroundColor: colors.surface,
                            color: colors.text,
                            fontSize: "14px",
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
                        <span
                          style={{
                            fontSize: "13px",
                            color: colors.muted,
                            display: "block",
                            marginBottom: "4px",
                          }}
                        >
                          Order
                        </span>
                        <select
                          value={quantFilters.sort_order || "asc"}
                          onChange={(e) =>
                            setQuantFilters({
                              ...quantFilters,
                              sort_order: e.target.value,
                            })
                          }
                          style={{
                            width: "100%",
                            padding: "8px 10px",
                            borderRadius: "8px",
                            border: `1px solid ${colors.border}`,
                            backgroundColor: colors.surface,
                            color: colors.text,
                            fontSize: "14px",
                          }}
                        >
                          <option value="asc">Asc</option>
                          <option value="desc">Desc</option>
                        </select>
                      </div>
                    </div>

                    {/* Earnings Within */}
                    <div style={{ marginBottom: "8px" }}>
                      <div
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          marginBottom: "4px",
                        }}
                      >
                        <span style={{ fontSize: "13px", color: colors.muted }}>
                          Earnings Within
                        </span>
                        <span
                          style={{
                            fontSize: "13px",
                            fontWeight: 600,
                            color: "#10B981",
                          }}
                        >
                          {quantFilters.earnings_within_days != null
                            ? quantFilters.earnings_within_days === 0
                              ? "None"
                              : `${quantFilters.earnings_within_days}d`
                            : "Any"}
                        </span>
                      </div>
                      <input
                        type="range"
                        min={0}
                        max={30}
                        step={1}
                        value={quantFilters.earnings_within_days ?? 0}
                        onChange={(e) => {
                          const val = parseInt(e.target.value, 10);
                          setQuantFilters({
                            ...quantFilters,
                            earnings_within_days: val === 0 ? null : val,
                          });
                        }}
                        style={{
                          width: "100%",
                          height: "4px",
                          appearance: "none",
                          backgroundColor: "rgba(255,255,255,0.1)",
                          borderRadius: "2px",
                        }}
                      />
                      <span style={{ fontSize: "11px", color: colors.subtle }}>
                        0 = Any, 1 = Tomorrow, 30 = Within 30 days
                      </span>
                    </div>

                    {/* Max Results */}
                    <div style={{ marginBottom: "8px" }}>
                      <span
                        style={{
                          fontSize: "13px",
                          color: colors.muted,
                          display: "block",
                          marginBottom: "4px",
                        }}
                      >
                        Max Results
                      </span>
                      <input
                        type="number"
                        min={1}
                        max={100}
                        value={quantFilters.max_results || 20}
                        onChange={(e) =>
                          setQuantFilters({
                            ...quantFilters,
                            max_results: parseInt(e.target.value, 10),
                          })
                        }
                        style={{
                          width: "100%",
                          padding: "8px 10px",
                          borderRadius: "8px",
                          border: `1px solid ${colors.border}`,
                          backgroundColor: colors.surface,
                          color: colors.text,
                          fontSize: "14px",
                        }}
                      />
                    </div>

                    {/* Live Summary */}
                    <div
                      style={{
                        marginTop: "12px",
                        padding: "10px",
                        borderRadius: "8px",
                        backgroundColor: "rgba(16,185,129,0.1)",
                        fontSize: "13px",
                        color: "#10B981",
                        lineHeight: 1.4,
                      }}
                    >
                      <strong>Active filters:</strong>{" "}
                      {quantFilters.ath_proximity_min != null &&
                        `ATH ≥ ${(quantFilters.ath_proximity_min * 100).toFixed(0)}% `}
                      {quantFilters.volume_ratio_min != null &&
                        `Vol ≥ ${quantFilters.volume_ratio_min}x `}
                      {(quantFilters.indicator_filters || []).map(
                        (item: any) => {
                          if (item.condition && item.reference_column) {
                            const tol =
                              item.condition === "equals" &&
                              item.tolerance !== undefined
                                ? ` (±${item.tolerance})`
                                : "";
                            return `${item.column} ${item.condition} ${item.reference_column}${tol} `;
                          }
                          const parts = [];
                          if (item.min != null) parts.push(`≥${item.min}`);
                          if (item.max != null) parts.push(`≤${item.max}`);
                          return parts.length > 0
                            ? `${item.column} ${parts.join(" ")} `
                            : "";
                        },
                      )}
                      | Sort: {quantFilters.sort_by || "ticker"}{" "}
                      {quantFilters.sort_order || "asc"}| Max:{" "}
                      {quantFilters.max_results || 20}
                    </div>
                  </div>
                )}

                {/* Base Setup Weight — Quant Strategy only */}
                {selectedMode === "quant_strategy" && (
                  <div
                    style={{
                      marginTop: "20px",
                      paddingTop: "20px",
                      borderTop: `1px solid ${colors.border}`,
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        marginBottom: "8px",
                      }}
                    >
                      <span
                        style={{
                          fontSize: "13px",
                          fontWeight: 600,
                          color: colors.text,
                        }}
                      >
                        Scoring Split
                      </span>
                      <span
                        style={{
                          fontSize: "13px",
                          fontWeight: 700,
                          color: "#10B981",
                        }}
                      >
                        {baseWeight}% Base / {100 - baseWeight}% Filter
                      </span>
                    </div>
                    <input
                      type="range"
                      min={0}
                      max={100}
                      step={5}
                      value={baseWeight}
                      onChange={(e) =>
                        setBaseWeight(parseInt(e.target.value, 10))
                      }
                      style={{
                        width: "100%",
                        height: "4px",
                        appearance: "none",
                        backgroundColor: "rgba(255,255,255,0.1)",
                        borderRadius: "2px",
                        cursor: "pointer",
                      }}
                    />
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        marginTop: "6px",
                      }}
                    >
                      <span style={{ fontSize: "11px", color: colors.muted }}>
                        0% — Pure filter match
                      </span>
                      <span style={{ fontSize: "11px", color: colors.muted }}>
                        100% — Pure setup quality
                      </span>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Thresholds - Conditional */}
            <div
              style={{
                padding: "32px",
                borderRadius: "20px",
                border: `1px solid ${colors.border}`,
                backgroundColor: colors.surface,
                opacity: selectedMode === "dormant_giant" ? 1 : 0.4,
                transition: "opacity 200ms ease",
              }}
            >
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  gap: "12px",
                  marginBottom: "24px",
                }}
              >
                <div
                  style={{
                    width: "36px",
                    height: "36px",
                    borderRadius: "10px",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    backgroundColor: "rgba(255,255,255,0.05)",
                  }}
                >
                  <SlidersHorizontal
                    style={{
                      width: "18px",
                      height: "18px",
                      color: colors.subtle,
                    }}
                  />
                </div>
                <div style={{ textAlign: "center" }}>
                  <span
                    style={{
                      fontSize: "17px",
                      fontWeight: 600,
                      letterSpacing: "-0.022em",
                      color: colors.text,
                    }}
                  >
                    Thresholds
                  </span>
                  {selectedMode !== "dormant_giant" && (
                    <span
                      style={{
                        ...LABEL_STYLE,
                        display: "block",
                        marginTop: "2px",
                      }}
                    >
                      Dormant Giant only
                    </span>
                  )}
                </div>
              </div>

              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: "24px",
                }}
              >
                {[
                  {
                    key: "consolidation_days" as const,
                    label: "Consolidation Tightness",
                    description: "Days price stays within 3% of 20-day SMA",
                    min: 10,
                    max: 20,
                    step: 1,
                    format: (v: number) => `${v} days`,
                  },
                  {
                    key: "mfi_threshold" as const,
                    label: "MFI Accumulation",
                    description:
                      "Money Flow Index threshold (volume-weighted RSI)",
                    min: 45,
                    max: 70,
                    step: 1,
                    format: (v: number) => `${v}`,
                  },
                  {
                    key: "volume_cluster_days" as const,
                    label: "Volume Cluster",
                    description:
                      "Days with volume > 1.2x average (out of last 5)",
                    min: 2,
                    max: 5,
                    step: 1,
                    format: (v: number) => `${v} days`,
                  },
                  {
                    key: "rs_minimum" as const,
                    label: "RS vs Market",
                    description:
                      "Minimum relative strength ratio vs market (sector ETF proxy)",
                    min: 0.5,
                    max: 1.2,
                    step: 0.05,
                    format: (v: number) => v.toFixed(2),
                  },
                ].map((slider) => (
                  <div key={slider.key}>
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        marginBottom: "4px",
                      }}
                    >
                      <div>
                        <span style={LABEL_STYLE}>{slider.label}</span>
                        <span
                          style={{
                            ...LABEL_STYLE,
                            color: colors.subtle,
                            marginLeft: "8px",
                          }}
                        >
                          {slider.description}
                        </span>
                      </div>
                      <span
                        style={{
                          fontSize: "17px",
                          fontWeight: 600,
                          fontVariantNumeric: "tabular-nums",
                          color: "#10B981",
                        }}
                      >
                        {slider.format(filters[slider.key] as number)}
                      </span>
                    </div>
                    <input
                      type="range"
                      min={slider.min}
                      max={slider.max}
                      step={slider.step}
                      value={filters[slider.key] as number}
                      onChange={(e) =>
                        setFilters({
                          ...filters,
                          [slider.key]: parseFloat(e.target.value),
                        })
                      }
                      disabled={selectedMode !== "dormant_giant"}
                      style={{
                        width: "100%",
                        height: "4px",
                        appearance: "none",
                        backgroundColor:
                          selectedMode === "dormant_giant"
                            ? "rgba(255,255,255,0.1)"
                            : "rgba(255,255,255,0.05)",
                        borderRadius: "2px",
                        outline: "none",
                        cursor:
                          selectedMode === "dormant_giant"
                            ? "pointer"
                            : "not-allowed",
                      }}
                    />
                  </div>
                ))}

                {/* Sector momentum toggle */}
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    padding: "12px 0",
                  }}
                >
                  <div>
                    <span style={LABEL_STYLE}>Sector Momentum Gate</span>
                    <span
                      style={{
                        ...LABEL_STYLE,
                        color: colors.subtle,
                        marginLeft: "8px",
                        display: "block",
                      }}
                    >
                      Only scan stocks in sectors above their 50-day SMA
                    </span>
                  </div>
                  <button
                    onClick={() =>
                      setFilters({
                        ...filters,
                        use_sector_momentum: !filters.use_sector_momentum,
                      })
                    }
                    disabled={selectedMode !== "dormant_giant"}
                    style={{
                      width: "48px",
                      height: "28px",
                      borderRadius: "14px",
                      border: "none",
                      cursor:
                        selectedMode === "dormant_giant"
                          ? "pointer"
                          : "not-allowed",
                      backgroundColor: filters.use_sector_momentum
                        ? "#10B981"
                        : "rgba(255,255,255,0.1)",
                      position: "relative",
                      transition: "background-color 200ms ease",
                    }}
                  >
                    <div
                      style={{
                        width: "22px",
                        height: "22px",
                        borderRadius: "11px",
                        backgroundColor: "#fff",
                        position: "absolute",
                        top: "3px",
                        left: filters.use_sector_momentum ? "23px" : "3px",
                        transition: "left 200ms ease",
                      }}
                    />
                  </button>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* === ACTION BAR === */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: "16px",
            marginBottom: "48px",
          }}
        >
          <button
            onClick={startScan}
            disabled={isScanning}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "10px",
              padding: "14px 32px",
              borderRadius: "999px",
              border: "none",
              backgroundColor: isScanning ? colors.subtle : "#10B981",
              color: isScanning ? colors.text : "#000000",
              fontSize: "17px",
              fontWeight: 600,
              letterSpacing: "-0.022em",
              cursor: isScanning ? "not-allowed" : "pointer",
              transition: "all 150ms ease",
              opacity: isScanning ? 0.6 : 1,
            }}
            onMouseEnter={(e) => {
              if (!isScanning) {
                e.currentTarget.style.backgroundColor = "#34D399";
                e.currentTarget.style.transform = "translateY(-1px)";
              }
            }}
            onMouseLeave={(e) => {
              if (!isScanning) {
                e.currentTarget.style.backgroundColor = "#10B981";
                e.currentTarget.style.transform = "translateY(0)";
              }
            }}
          >
            {isScanning ? (
              <Loader2
                style={{ width: "18px", height: "18px" }}
                className="animate-spin"
              />
            ) : (
              <Search style={{ width: "18px", height: "18px" }} />
            )}
            {isScanning ? `Scanning... ${progress}%` : "Start Screen"}
          </button>

          {isScanning && (
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "8px",
              }}
            >
              <div
                style={{
                  width: "160px",
                  height: "4px",
                  borderRadius: "2px",
                  backgroundColor: "rgba(255,255,255,0.08)",
                  overflow: "hidden",
                }}
              >
                <div
                  style={{
                    width: `${progress}%`,
                    height: "100%",
                    backgroundColor: "#10B981",
                    borderRadius: "2px",
                    transition: "width 300ms ease",
                  }}
                />
              </div>
              <span style={{ ...LABEL_STYLE }}>{progress}%</span>
            </div>
          )}

          {/* Terminal toggle */}
          <button
            onClick={() => setShowTerminal(!showTerminal)}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              padding: "8px 16px",
              borderRadius: "14px",
              border: `1px solid ${colors.border}`,
              backgroundColor: "transparent",
              color: colors.muted,
              fontSize: "13px",
              fontWeight: 600,
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
            <Terminal style={{ width: "14px", height: "14px" }} />
            {showTerminal ? "Hide Logs" : "Show Logs"}
          </button>
        </div>

        {/* === TERMINAL: xterm.js === */}
        <AnimatePresence>
          {showTerminal && (
            <TerminalLog
              logs={logs}
              style={{
                marginBottom: "32px",
                borderRadius: "14px",
                overflow: "hidden",
                border: `1px solid ${colors.border}`,
                maxHeight: "320px",
              }}
            />
          )}
        </AnimatePresence>

        {/* === RESULTS === */}
        {(results.length > 0 || aiReport) && (
          <div
            style={{
              paddingTop: "48px",
              borderTop: `1px solid ${colors.border}`,
              marginBottom: "48px",
            }}
          >
            {/* AI Report */}
            <AnimatePresence>
              {aiReport && (
                <div style={{ marginBottom: "48px" }}>
                  <div
                    style={{
                      padding: "32px",
                      borderRadius: "20px",
                      border: `1px solid ${colors.border}`,
                      backgroundColor: colors.surfaceRaised,
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        gap: "16px",
                        marginBottom: "16px",
                      }}
                    >
                      <div
                        style={{
                          width: "40px",
                          height: "40px",
                          borderRadius: "10px",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          backgroundColor: "rgba(16,185,129,0.15)",
                        }}
                      >
                        <Cpu
                          style={{
                            width: "20px",
                            height: "20px",
                            color: "#10B981",
                          }}
                        />
                      </div>
                      <div>
                        <h3
                          style={{
                            fontSize: "21px",
                            fontWeight: 600,
                            letterSpacing: "-0.02em",
                            color: colors.text,
                            margin: 0,
                          }}
                        >
                          Analysis Report
                        </h3>
                      </div>
                      <button
                        onClick={() => setShowReport(!showReport)}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: "6px",
                          padding: "8px 16px",
                          borderRadius: "14px",
                          border: `1px solid ${colors.border}`,
                          backgroundColor: "transparent",
                          color: colors.muted,
                          fontSize: "13px",
                          fontWeight: 600,
                          cursor: "pointer",
                          transition: "all 150ms ease",
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.borderColor =
                            colors.borderHover;
                          e.currentTarget.style.color = colors.text;
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.borderColor = colors.border;
                          e.currentTarget.style.color = colors.muted;
                        }}
                      >
                        {showReport ? "Collapse" : "Expand"}
                        <ChevronDown
                          style={{
                            width: "14px",
                            height: "14px",
                            transition: "transform 150ms ease",
                            transform: showReport
                              ? "rotate(180deg)"
                              : "rotate(0)",
                          }}
                        />
                      </button>
                    </div>

                    <AnimatePresence>
                      {showReport && (
                        <div
                          style={{
                            padding: "16px",
                            borderRadius: "10px",
                            backgroundColor: "#000000",
                            border: `1px solid ${colors.border}`,
                          }}
                        >
                          <pre
                            style={{
                              whiteSpace: "pre-wrap",
                              fontSize: "14px",
                              fontFamily:
                                "JetBrains Mono, Fira Code, monospace",
                              lineHeight: 1.5,
                              color: colors.muted,
                              margin: 0,
                            }}
                          >
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
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    gap: "12px",
                    marginBottom: "24px",
                  }}
                >
                  <h2 style={{ ...SECTION_HEADING, marginBottom: 0 }}>
                    {results.length} Targets
                  </h2>
                  <span
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "4px",
                      padding: "4px 12px",
                      borderRadius: "999px",
                      backgroundColor: "rgba(16,185,129,0.1)",
                      color: "#10B981",
                      fontSize: "12px",
                      fontWeight: 600,
                      letterSpacing: "0.05em",
                    }}
                  >
                    <CheckCircle2 style={{ width: "12px", height: "12px" }} />
                    Verified
                  </span>

                  {/* PDF download */}
                  <button
                    onClick={downloadPDF}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "6px",
                      padding: "8px 16px",
                      borderRadius: "14px",
                      border: `1px solid ${colors.border}`,
                      backgroundColor: "transparent",
                      color: colors.muted,
                      fontSize: "13px",
                      fontWeight: 600,
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
                    <FileDown style={{ width: "14px", height: "14px" }} />
                    PDF Report
                  </button>

                  {/* Clear Results */}
                  <button
                    onClick={exportToQuantGen}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "6px",
                      padding: "8px 16px",
                      borderRadius: "14px",
                      border: `1px solid ${colors.border}`,
                      backgroundColor: "transparent",
                      color: colors.muted,
                      fontSize: "13px",
                      fontWeight: 600,
                      cursor: "pointer",
                      transition: "all 150ms ease",
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.borderColor =
                        "rgba(16,185,129,0.4)";
                      e.currentTarget.style.color = "#10B981";
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.borderColor = colors.border;
                      e.currentTarget.style.color = colors.muted;
                    }}
                  >
                    <ArrowRight style={{ width: "14px", height: "14px" }} />
                    Export to QuantGen
                  </button>

                  <button
                    onClick={clearResults}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "6px",
                      padding: "8px 16px",
                      borderRadius: "14px",
                      border: `1px solid ${colors.border}`,
                      backgroundColor: "transparent",
                      color: colors.muted,
                      fontSize: "13px",
                      fontWeight: 600,
                      cursor: "pointer",
                      transition: "all 150ms ease",
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.borderColor = "rgba(239,68,68,0.3)";
                      e.currentTarget.style.color = "#EF4444";
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.borderColor = colors.border;
                      e.currentTarget.style.color = colors.muted;
                    }}
                  >
                    <X style={{ width: "14px", height: "14px" }} />
                    Clear
                  </button>
                </div>

                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(3, 1fr)",
                    gap: "16px",
                  }}
                >
                  {results.map((result) => (
                    <div
                      key={result.ticker}
                      onClick={() => openChart(result.ticker)}
                      style={{
                        padding: "24px",
                        borderRadius: "20px",
                        border: `1px solid ${colors.border}`,
                        backgroundColor: colors.surface,
                        cursor: "pointer",
                        transition: "all 150ms ease",
                        display: "flex",
                        flexDirection: "column",
                        gap: "16px",
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.borderColor =
                          "rgba(16,185,129,0.4)";
                        e.currentTarget.style.backgroundColor =
                          colors.surfaceRaised;
                        e.currentTarget.style.transform = "translateY(-2px)";
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.borderColor = colors.border;
                        e.currentTarget.style.backgroundColor = colors.surface;
                        e.currentTarget.style.transform = "translateY(0)";
                      }}
                    >
                      {/* Header: Ticker + Signal Circle */}
                      <div
                        style={{
                          display: "flex",
                          alignItems: "flex-start",
                          justifyContent: "space-between",
                          width: "100%",
                        }}
                      >
                        <div
                          style={{
                            display: "flex",
                            flexDirection: "column",
                            gap: "2px",
                          }}
                        >
                          <div
                            style={{
                              display: "flex",
                              alignItems: "center",
                              gap: "8px",
                            }}
                          >
                            <h3
                              style={{
                                fontSize: "22px",
                                fontWeight: 600,
                                letterSpacing: "-0.02em",
                                color: colors.text,
                                margin: 0,
                              }}
                            >
                              {result.ticker}
                            </h3>
                            {(() => {
                              const close = result.close;
                              const sma20 = result.sma_20;
                              const ema9 = result.ema_9;
                              let signalColor: string | null = null;
                              if (close && sma20 && ema9) {
                                if (close > sma20 && close > ema9)
                                  signalColor = "#10B981";
                                else if (close < sma20 && close < ema9)
                                  signalColor = "#EF4444";
                                else signalColor = "#FBBF24";
                              }
                              return signalColor ? (
                                <div
                                  style={{
                                    width: "14px",
                                    height: "14px",
                                    borderRadius: "50%",
                                    backgroundColor: signalColor,
                                    boxShadow: `0 0 6px ${signalColor}`,
                                    flexShrink: 0,
                                  }}
                                />
                              ) : null;
                            })()}
                          </div>
                          {result.company_name &&
                            result.company_name !== result.ticker && (
                              <span
                                style={{
                                  fontSize: "13px",
                                  fontWeight: 500,
                                  color: colors.muted,
                                  lineHeight: 1.3,
                                  maxWidth: "180px",
                                  overflow: "hidden",
                                  textOverflow: "ellipsis",
                                  whiteSpace: "nowrap",
                                }}
                              >
                                {result.company_name}
                              </span>
                            )}
                        </div>
                        {result.sector && result.sector !== "N/A" && (
                          <span
                            style={{
                              fontSize: "10px",
                              fontWeight: 600,
                              letterSpacing: "0.08em",
                              textTransform: "uppercase",
                              padding: "3px 10px",
                              borderRadius: "999px",
                              backgroundColor: "rgba(255,255,255,0.05)",
                              border: `1px solid ${colors.border}`,
                              color: colors.subtle,
                              flexShrink: 0,
                            }}
                          >
                            {result.sector}
                          </span>
                        )}
                      </div>

                      {/* Score Badge */}
                      {result.score != null && (
                        <div
                          style={{
                            display: "flex",
                            justifyContent: "center",
                            marginBottom: "4px",
                          }}
                        >
                          <ScoreBadge score={result.score} />
                        </div>
                      )}

                      {/* Base Setup Breakdown */}
                      {(result.trend_score != null ||
                        result.momentum_score != null ||
                        result.volatility_score != null ||
                        result.volume_score != null) && (
                        <div
                          style={{
                            display: "grid",
                            gridTemplateColumns: "repeat(4, 1fr)",
                            gap: "4px",
                            marginBottom: "8px",
                          }}
                        >
                          {[
                            { label: "Trend", value: result.trend_score },
                            { label: "Momentum", value: result.momentum_score },
                            {
                              label: "Volatility",
                              value: result.volatility_score,
                            },
                            { label: "Volume", value: result.volume_score },
                          ].map((item) => (
                            <div
                              key={item.label}
                              style={{ textAlign: "center" }}
                            >
                              <div
                                style={{
                                  fontSize: "10px",
                                  fontWeight: 600,
                                  color: colors.muted,
                                  letterSpacing: "0.04em",
                                }}
                              >
                                {item.label}
                              </div>
                              <div
                                style={{
                                  fontSize: "13px",
                                  fontWeight: 700,
                                  fontVariantNumeric: "tabular-nums",
                                  color:
                                    (item.value ?? 0) >= 70
                                      ? "#10B981"
                                      : (item.value ?? 0) >= 50
                                        ? "#F59E0B"
                                        : "#EF4444",
                                }}
                              >
                                {(item.value ?? 0).toFixed(0)}
                              </div>
                            </div>
                          ))}
                        </div>
                      )}

                      {/* Price */}
                      {result.close && (
                        <div style={{ textAlign: "center" }}>
                          <p
                            style={{
                              fontSize: "28px",
                              fontWeight: 600,
                              letterSpacing: "-0.02em",
                              fontVariantNumeric: "tabular-nums",
                              color: colors.text,
                              margin: 0,
                            }}
                          >
                            ${result.close.toFixed(2)}
                          </p>
                          {(result.high_52w || result.low_52w) && (
                            <div
                              style={{
                                display: "flex",
                                justifyContent: "center",
                                gap: "12px",
                                marginTop: "4px",
                              }}
                            >
                              {result.low_52w && (
                                <span
                                  style={{
                                    fontSize: "11px",
                                    color: colors.subtle,
                                  }}
                                >
                                  52W Low ${result.low_52w.toFixed(2)}
                                </span>
                              )}
                              {result.high_52w && (
                                <span
                                  style={{
                                    fontSize: "11px",
                                    color: colors.subtle,
                                  }}
                                >
                                  52W High ${result.high_52w.toFixed(2)}
                                </span>
                              )}
                            </div>
                          )}
                        </div>
                      )}

                      {/* Signal + Catalyst */}
                      {result.signal && (
                        <span
                          style={{
                            fontSize: "13px",
                            fontWeight: 600,
                            letterSpacing: "0.05em",
                            color: "#10B981",
                            textAlign: "center",
                          }}
                        >
                          {result.signal}
                        </span>
                      )}

                      {result.fundamental_catalyst && (
                        <div
                          style={{
                            padding: "10px 14px",
                            borderRadius: "10px",
                            backgroundColor: "rgba(16,185,129,0.04)",
                            border: "1px solid rgba(16,185,129,0.15)",
                            textAlign: "center",
                          }}
                        >
                          <p
                            style={{
                              fontSize: "13px",
                              lineHeight: 1.4,
                              color: "rgba(16,185,129,0.9)",
                              margin: 0,
                            }}
                          >
                            {result.fundamental_catalyst}
                          </p>
                        </div>
                      )}

                      {/* Price Stats */}
                      {(result.high_52w ||
                        result.low_52w ||
                        result.all_time_high ||
                        result.all_time_low ||
                        result.ath_proximity ||
                        result.volume_ratio) && (
                        <div
                          style={{
                            display: "grid",
                            gridTemplateColumns: "repeat(2, 1fr)",
                            gap: "8px",
                            paddingTop: "12px",
                            borderTop: `1px solid ${colors.border}`,
                            textAlign: "center",
                          }}
                        >
                          {result.high_52w !== undefined && (
                            <div>
                              <span
                                style={{
                                  ...LABEL_STYLE,
                                  display: "block",
                                  marginBottom: "2px",
                                  fontSize: "10px",
                                }}
                              >
                                52W High
                              </span>
                              <span
                                style={{
                                  fontSize: "15px",
                                  fontWeight: 600,
                                  fontVariantNumeric: "tabular-nums",
                                  color: colors.text,
                                }}
                              >
                                ${result.high_52w.toFixed(2)}
                              </span>
                            </div>
                          )}
                          {result.low_52w !== undefined && (
                            <div>
                              <span
                                style={{
                                  ...LABEL_STYLE,
                                  display: "block",
                                  marginBottom: "2px",
                                  fontSize: "10px",
                                }}
                              >
                                52W Low
                              </span>
                              <span
                                style={{
                                  fontSize: "15px",
                                  fontWeight: 600,
                                  fontVariantNumeric: "tabular-nums",
                                  color: colors.text,
                                }}
                              >
                                ${result.low_52w.toFixed(2)}
                              </span>
                            </div>
                          )}
                          {result.all_time_high !== undefined && (
                            <div>
                              <span
                                style={{
                                  ...LABEL_STYLE,
                                  display: "block",
                                  marginBottom: "2px",
                                  fontSize: "10px",
                                }}
                              >
                                ATH
                              </span>
                              <span
                                style={{
                                  fontSize: "15px",
                                  fontWeight: 600,
                                  fontVariantNumeric: "tabular-nums",
                                  color: colors.text,
                                }}
                              >
                                ${result.all_time_high.toFixed(2)}
                              </span>
                            </div>
                          )}
                          {result.all_time_low !== undefined && (
                            <div>
                              <span
                                style={{
                                  ...LABEL_STYLE,
                                  display: "block",
                                  marginBottom: "2px",
                                  fontSize: "10px",
                                }}
                              >
                                ATL
                              </span>
                              <span
                                style={{
                                  fontSize: "15px",
                                  fontWeight: 600,
                                  fontVariantNumeric: "tabular-nums",
                                  color: colors.text,
                                }}
                              >
                                ${result.all_time_low.toFixed(2)}
                              </span>
                            </div>
                          )}
                          {result.ath_proximity != null && (
                            <div>
                              <span
                                style={{
                                  ...LABEL_STYLE,
                                  display: "block",
                                  marginBottom: "2px",
                                  fontSize: "10px",
                                }}
                              >
                                ATH Proximity
                              </span>
                              <span
                                style={{
                                  fontSize: "15px",
                                  fontWeight: 600,
                                  fontVariantNumeric: "tabular-nums",
                                  color: "#10B981",
                                }}
                              >
                                {(result.ath_proximity * 100).toFixed(1)}%
                              </span>
                            </div>
                          )}
                          {result.volume_ratio != null && (
                            <div>
                              <span
                                style={{
                                  ...LABEL_STYLE,
                                  display: "block",
                                  marginBottom: "2px",
                                  fontSize: "10px",
                                }}
                              >
                                Vol Ratio
                              </span>
                              <span
                                style={{
                                  fontSize: "15px",
                                  fontWeight: 600,
                                  fontVariantNumeric: "tabular-nums",
                                  color: "#3B82F6",
                                }}
                              >
                                {result.volume_ratio.toFixed(2)}x
                              </span>
                            </div>
                          )}
                        </div>
                      )}

                      {/* Volume */}
                      {(result.volume != null ||
                        result.volume_ma_50 != null) && (
                        <div
                          style={{
                            display: "grid",
                            gridTemplateColumns: "repeat(2, 1fr)",
                            gap: "8px",
                            paddingTop: "12px",
                            borderTop: `1px solid ${colors.border}`,
                            textAlign: "center",
                          }}
                        >
                          {result.volume != null && (
                            <div>
                              <span
                                style={{
                                  ...LABEL_STYLE,
                                  display: "block",
                                  marginBottom: "2px",
                                  fontSize: "10px",
                                }}
                              >
                                Volume
                              </span>
                              <span
                                style={{
                                  fontSize: "15px",
                                  fontWeight: 600,
                                  fontVariantNumeric: "tabular-nums",
                                  color: "#3B82F6",
                                }}
                              >
                                {result.volume.toLocaleString()}
                              </span>
                            </div>
                          )}
                          {result.volume_ma_50 != null && (
                            <div>
                              <span
                                style={{
                                  ...LABEL_STYLE,
                                  display: "block",
                                  marginBottom: "2px",
                                  fontSize: "10px",
                                }}
                              >
                                Vol MA(50)
                              </span>
                              <span
                                style={{
                                  fontSize: "15px",
                                  fontWeight: 600,
                                  fontVariantNumeric: "tabular-nums",
                                  color: "#8B5CF6",
                                }}
                              >
                                {Math.round(
                                  result.volume_ma_50,
                                ).toLocaleString()}
                              </span>
                            </div>
                          )}
                        </div>
                      )}

                      {/* Fundamentals */}
                      {(result.eps_growth_qoq !== undefined ||
                        result.revenue_growth_qoq !== undefined ||
                        result.peg_ratio !== undefined ||
                        result.beta !== undefined) && (
                        <div
                          style={{
                            display: "grid",
                            gridTemplateColumns: "repeat(2, 1fr)",
                            gap: "8px",
                            paddingTop: "12px",
                            borderTop: `1px solid ${colors.border}`,
                            textAlign: "center",
                          }}
                        >
                          {result.eps_growth_qoq != null && (
                            <div>
                              <span
                                style={{
                                  ...LABEL_STYLE,
                                  display: "block",
                                  marginBottom: "2px",
                                  fontSize: "10px",
                                }}
                              >
                                EPS Growth
                              </span>
                              <span
                                style={{
                                  fontSize: "15px",
                                  fontWeight: 600,
                                  fontVariantNumeric: "tabular-nums",
                                  color: colors.text,
                                }}
                              >
                                {result.eps_growth_qoq.toFixed(1)}%
                              </span>
                            </div>
                          )}
                          {result.revenue_growth_qoq != null && (
                            <div>
                              <span
                                style={{
                                  ...LABEL_STYLE,
                                  display: "block",
                                  marginBottom: "2px",
                                  fontSize: "10px",
                                }}
                              >
                                Rev Growth
                              </span>
                              <span
                                style={{
                                  fontSize: "15px",
                                  fontWeight: 600,
                                  fontVariantNumeric: "tabular-nums",
                                  color: colors.text,
                                }}
                              >
                                {result.revenue_growth_qoq.toFixed(1)}%
                              </span>
                            </div>
                          )}
                          {result.peg_ratio != null && (
                            <div>
                              <span
                                style={{
                                  ...LABEL_STYLE,
                                  display: "block",
                                  marginBottom: "2px",
                                  fontSize: "10px",
                                }}
                              >
                                PEG
                              </span>
                              <span
                                style={{
                                  fontSize: "15px",
                                  fontWeight: 600,
                                  fontVariantNumeric: "tabular-nums",
                                  color: colors.text,
                                }}
                              >
                                {result.peg_ratio.toFixed(2)}
                              </span>
                            </div>
                          )}
                          {result.beta != null && (
                            <div>
                              <span
                                style={{
                                  ...LABEL_STYLE,
                                  display: "block",
                                  marginBottom: "2px",
                                  fontSize: "10px",
                                }}
                              >
                                Beta
                              </span>
                              <span
                                style={{
                                  fontSize: "15px",
                                  fontWeight: 600,
                                  fontVariantNumeric: "tabular-nums",
                                  color: colors.text,
                                }}
                              >
                                {result.beta.toFixed(2)}
                              </span>
                            </div>
                          )}
                          {result.days_until_earnings != null && (
                            <div>
                              <span
                                style={{
                                  ...LABEL_STYLE,
                                  display: "block",
                                  marginBottom: "2px",
                                  fontSize: "10px",
                                }}
                              >
                                Next Earnings
                              </span>
                              <span
                                style={{
                                  fontSize: "15px",
                                  fontWeight: 600,
                                  fontVariantNumeric: "tabular-nums",
                                  color:
                                    result.days_until_earnings <= 3
                                      ? "#EF4444"
                                      : result.days_until_earnings <= 7
                                        ? "#F59E0B"
                                        : "#10B981",
                                }}
                              >
                                {result.days_until_earnings === 0
                                  ? "Today"
                                  : result.days_until_earnings === 1
                                    ? "Tomorrow"
                                    : `${result.days_until_earnings}d`}
                              </span>
                            </div>
                          )}
                        </div>
                      )}

                      {/* Technicals */}
                      {(result.sma_20 != null ||
                        result.ema_9 != null ||
                        result.rsi != null ||
                        result.macd != null) && (
                        <div
                          style={{
                            display: "grid",
                            gridTemplateColumns: "repeat(2, 1fr)",
                            gap: "8px",
                            paddingTop: "12px",
                            borderTop: `1px solid ${colors.border}`,
                            textAlign: "center",
                          }}
                        >
                          {result.sma_20 != null && (
                            <div>
                              <span
                                style={{
                                  ...LABEL_STYLE,
                                  display: "block",
                                  marginBottom: "2px",
                                  fontSize: "10px",
                                }}
                              >
                                SMA(20)
                              </span>
                              <span
                                style={{
                                  fontSize: "15px",
                                  fontWeight: 600,
                                  fontVariantNumeric: "tabular-nums",
                                  color: colors.text,
                                }}
                              >
                                {result.sma_20.toFixed(2)}
                              </span>
                            </div>
                          )}
                          {result.ema_9 != null && (
                            <div>
                              <span
                                style={{
                                  ...LABEL_STYLE,
                                  display: "block",
                                  marginBottom: "2px",
                                  fontSize: "10px",
                                }}
                              >
                                EMA(9)
                              </span>
                              <span
                                style={{
                                  fontSize: "15px",
                                  fontWeight: 600,
                                  fontVariantNumeric: "tabular-nums",
                                  color: colors.text,
                                }}
                              >
                                {result.ema_9.toFixed(2)}
                              </span>
                            </div>
                          )}
                          {result.rsi != null && (
                            <div>
                              <span
                                style={{
                                  ...LABEL_STYLE,
                                  display: "block",
                                  marginBottom: "2px",
                                  fontSize: "10px",
                                }}
                              >
                                RSI(14)
                              </span>
                              <span
                                style={{
                                  fontSize: "15px",
                                  fontWeight: 600,
                                  fontVariantNumeric: "tabular-nums",
                                  color: colors.text,
                                }}
                              >
                                {result.rsi.toFixed(1)}
                              </span>
                            </div>
                          )}
                          {result.macd != null && (
                            <div>
                              <span
                                style={{
                                  ...LABEL_STYLE,
                                  display: "block",
                                  marginBottom: "2px",
                                  fontSize: "10px",
                                }}
                              >
                                MACD
                              </span>
                              <span
                                style={{
                                  fontSize: "15px",
                                  fontWeight: 600,
                                  fontVariantNumeric: "tabular-nums",
                                  color: colors.text,
                                }}
                              >
                                {result.macd.toFixed(3)}
                              </span>
                            </div>
                          )}
                        </div>
                      )}

                      {/* Signal Breakdown */}
                      {result.mfi != null && (
                        <div
                          style={{
                            marginTop: "12px",
                            padding: "12px",
                            borderRadius: "10px",
                            backgroundColor: colors.surfaceRaised,
                            border: `1px solid ${colors.border}`,
                          }}
                        >
                          <div
                            style={{
                              fontSize: "12px",
                              fontWeight: 600,
                              color: colors.muted,
                              marginBottom: "10px",
                            }}
                          >
                            Signal Breakdown
                          </div>
                          <div
                            style={{
                              display: "flex",
                              flexDirection: "column",
                              gap: "10px",
                            }}
                          >
                            {/* MFI */}
                            <div>
                              <div
                                style={{
                                  fontSize: "13px",
                                  fontWeight: 600,
                                  color: colors.text,
                                }}
                              >
                                MFI (Money Flow Index):{" "}
                                <span
                                  style={{
                                    color:
                                      result.mfi > 55 ? "#10B981" : "#EF4444",
                                  }}
                                >
                                  {result.mfi}
                                </span>
                              </div>
                              <div
                                style={{
                                  fontSize: "11px",
                                  color: colors.muted,
                                  lineHeight: 1.4,
                                  marginTop: "2px",
                                }}
                              >
                                Volume-weighted buying pressure (like RSI but
                                with volume). Above 55 means money is flowing in
                                = accumulation.
                              </div>
                            </div>
                            {/* Volume Cluster */}
                            <div>
                              <div
                                style={{
                                  fontSize: "13px",
                                  fontWeight: 600,
                                  color: colors.text,
                                }}
                              >
                                Volume Cluster:{" "}
                                <span
                                  style={{
                                    color:
                                      (result.volume_cluster_days || 0) >= 3
                                        ? "#10B981"
                                        : "#EF4444",
                                  }}
                                >
                                  {result.volume_cluster_days} days
                                </span>
                              </div>
                              <div
                                style={{
                                  fontSize: "11px",
                                  color: colors.muted,
                                  lineHeight: 1.4,
                                  marginTop: "2px",
                                }}
                              >
                                How many of the last 5 trading days had
                                unusually high volume (&gt;1.2x the 50-day
                                average). 3+ days suggests institutional buying.
                              </div>
                            </div>
                            {/* Relative Strength */}
                            <div>
                              <div
                                style={{
                                  fontSize: "13px",
                                  fontWeight: 600,
                                  color: colors.text,
                                }}
                              >
                                RS (Relative Strength):{" "}
                                <span
                                  style={{
                                    color:
                                      (result.rs_ratio || 0) >= 0.8
                                        ? "#10B981"
                                        : "#EF4444",
                                  }}
                                >
                                  {result.rs_ratio?.toFixed(2)}
                                </span>
                              </div>
                              <div
                                style={{
                                  fontSize: "11px",
                                  color: colors.muted,
                                  lineHeight: 1.4,
                                  marginTop: "2px",
                                }}
                              >
                                Stock's 20-day return vs the overall market
                                (equal-weighted sector ETF proxy). Above 0.8
                                means the stock is keeping pace with or
                                outperforming the market.
                              </div>
                            </div>
                            {/* Bandwidth */}
                            <div>
                              <div
                                style={{
                                  fontSize: "13px",
                                  fontWeight: 600,
                                  color: colors.text,
                                }}
                              >
                                Bandwidth:{" "}
                                <span
                                  style={{
                                    color:
                                      (result.bandwidth_pct || 100) < 20
                                        ? "#10B981"
                                        : "#EF4444",
                                  }}
                                >
                                  {result.bandwidth_pct?.toFixed(1)}%
                                </span>
                              </div>
                              <div
                                style={{
                                  fontSize: "11px",
                                  color: colors.muted,
                                  lineHeight: 1.4,
                                  marginTop: "2px",
                                }}
                              >
                                Where the current Bollinger Band width sits
                                within its 120-day range. Under 20% means the
                                stock is in a tight volatility squeeze = likely
                                to move soon.
                              </div>
                            </div>
                          </div>
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
          <div
            style={{
              textAlign: "center",
              paddingTop: "96px",
              paddingBottom: "96px",
            }}
          >
            <div
              style={{
                width: "48px",
                height: "48px",
                borderRadius: "14px",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                backgroundColor: "rgba(255,255,255,0.05)",
                border: `1px solid ${colors.border}`,
                margin: "0 auto 16px",
              }}
            >
              {scanCompleted ? (
                <Search
                  style={{
                    width: "20px",
                    height: "20px",
                    color: colors.subtle,
                  }}
                />
              ) : (
                <Sparkles
                  style={{
                    width: "20px",
                    height: "20px",
                    color: colors.subtle,
                  }}
                />
              )}
            </div>
            <p
              style={{
                fontSize: "17px",
                fontWeight: 600,
                letterSpacing: "-0.022em",
                color: colors.muted,
                margin: 0,
              }}
            >
              {scanCompleted
                ? "No stocks matched the filters"
                : "Select a mode and start a scan"}
            </p>
            <p
              style={{
                ...BODY_TEXT,
                fontSize: "14px",
                color: colors.subtle,
                marginTop: "4px",
              }}
            >
              {scanCompleted
                ? "Try relaxing the filter thresholds and run again"
                : "Press <kbd style={{ padding: '2px 6px', borderRadius: '4px', backgroundColor: 'rgba(255,255,255,0.08)', fontFamily: 'JetBrains Mono, monospace', fontSize: '12px' }}>S</kbd> to start"}
            </p>
          </div>
        )}

        {/* === FOOTER === */}
        <div
          style={{
            padding: "16px 0",
            borderTop: `1px solid ${colors.border}`,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: "24px",
            marginBottom: "16px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <span style={LABEL_STYLE}>System</span>
            <span
              style={{
                display: "flex",
                alignItems: "center",
                gap: "4px",
                padding: "3px 10px",
                borderRadius: "999px",
                backgroundColor: "rgba(16,185,129,0.1)",
                color: "#34D399",
                fontSize: "11px",
                fontWeight: 600,
                letterSpacing: "0.05em",
              }}
            >
              <span
                style={{
                  width: "5px",
                  height: "5px",
                  borderRadius: "50%",
                  backgroundColor: "#10B981",
                }}
              />
              Ready
            </span>
          </div>
          <span
            style={{
              ...LABEL_STYLE,
              fontSize: "11px",
              fontVariantNumeric: "tabular-nums",
            }}
          >
            {lastUpdated}
          </span>
        </div>
      </div>

      {/* Error Toast */}
      <AnimatePresence>
        {error && (
          <div
            style={{
              position: "fixed",
              bottom: "24px",
              left: "50%",
              transform: "translateX(-50%)",
              zIndex: 50,
              display: "flex",
              alignItems: "center",
              gap: "8px",
              padding: "12px 20px",
              borderRadius: "14px",
              backgroundColor: "rgba(239,68,68,0.1)",
              border: "1px solid rgba(239,68,68,0.2)",
            }}
          >
            <AlertCircle
              style={{ width: "18px", height: "18px", color: "#EF4444" }}
            />
            <span
              style={{ fontSize: "15px", fontWeight: 600, color: "#EF4444" }}
            >
              {error}
            </span>
          </div>
        )}
      </AnimatePresence>

      {/* Help Modal */}
      {showHelp && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 100,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            backgroundColor: "rgba(0,0,0,0.6)",
            padding: "24px",
          }}
          onClick={() => setShowHelp(false)}
        >
          <div
            style={{
              maxWidth: "640px",
              width: "100%",
              maxHeight: "80vh",
              overflow: "auto",
              backgroundColor: colors.surface,
              border: `1px solid ${colors.border}`,
              borderRadius: "20px",
              padding: "32px",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: "24px",
              }}
            >
              <h2
                style={{
                  fontSize: "21px",
                  fontWeight: 600,
                  color: colors.text,
                  margin: 0,
                }}
              >
                How Dormant Giant Works
              </h2>
              <button
                onClick={() => setShowHelp(false)}
                style={{
                  width: "32px",
                  height: "32px",
                  borderRadius: "8px",
                  border: "none",
                  backgroundColor: "transparent",
                  color: colors.muted,
                  cursor: "pointer",
                  fontSize: "18px",
                }}
              >
                ×
              </button>
            </div>

            <div
              style={{ display: "flex", flexDirection: "column", gap: "20px" }}
            >
              <section>
                <h3
                  style={{
                    fontSize: "15px",
                    fontWeight: 600,
                    color: colors.text,
                    marginBottom: "8px",
                  }}
                >
                  What is a Dormant Giant?
                </h3>
                <p
                  style={{
                    fontSize: "14px",
                    color: colors.muted,
                    lineHeight: 1.6,
                    margin: 0,
                  }}
                >
                  A stock that has been quietly building energy through a tight
                  consolidation (low volatility, flat price) while institutional
                  buyers accumulate shares beneath the surface. When the squeeze
                  resolves, the stock often explodes upward — that's the "giant
                  waking up."
                </p>
              </section>

              <section>
                <h3
                  style={{
                    fontSize: "15px",
                    fontWeight: 600,
                    color: colors.text,
                    marginBottom: "8px",
                  }}
                >
                  The 6 Signals
                </h3>
                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: "12px",
                  }}
                >
                  {[
                    {
                      name: "Bollinger Squeeze",
                      desc: "Bandwidth in the bottom 20% of its 120-day range and under 6%. True volatility contraction.",
                    },
                    {
                      name: "Consolidation Tightness",
                      desc: "Price stays within 3% of its 20-day SMA for at least 15 of the last 20 days. No drift.",
                    },
                    {
                      name: "MFI Accumulation",
                      desc: "Money Flow Index > 55. Volume-weighted RSI showing buying pressure.",
                    },
                    {
                      name: "Volume Cluster",
                      desc: "3+ of the last 5 days with volume > 1.2x average. Institutional footprints.",
                    },
                    {
                      name: "RS vs Market",
                      desc: "Stock's 20-day return vs equal-weighted sector ETF proxy. Avoids false breakouts into weakness.",
                    },
                    {
                      name: "Sector Momentum",
                      desc: "Parent sector ETF is above its 50-day SMA. Fish in rising water.",
                    },
                  ].map((signal) => (
                    <div
                      key={signal.name}
                      style={{
                        padding: "12px",
                        borderRadius: "10px",
                        backgroundColor: colors.surfaceRaised,
                      }}
                    >
                      <div
                        style={{
                          fontSize: "14px",
                          fontWeight: 600,
                          color: colors.text,
                        }}
                      >
                        {signal.name}
                      </div>
                      <div
                        style={{
                          fontSize: "13px",
                          color: colors.muted,
                          marginTop: "4px",
                        }}
                      >
                        {signal.desc}
                      </div>
                    </div>
                  ))}
                </div>
              </section>

              <section>
                <h3
                  style={{
                    fontSize: "15px",
                    fontWeight: 600,
                    color: colors.text,
                    marginBottom: "8px",
                  }}
                >
                  Composite Score (0-100)
                </h3>
                <p
                  style={{
                    fontSize: "14px",
                    color: colors.muted,
                    lineHeight: 1.6,
                    margin: 0,
                  }}
                >
                  Each passing stock receives an explosiveness score based on
                  all 6 signals.
                  <strong style={{ color: "#10B981" }}>Green (≥70)</strong> =
                  strong setup.
                  <strong style={{ color: "#F59E0B" }}>Yellow (50-69)</strong> =
                  moderate.
                  <strong style={{ color: "#EF4444" }}>Red (&lt;50)</strong> =
                  weaker but still passing.
                </p>
              </section>

              <section>
                <h3
                  style={{
                    fontSize: "15px",
                    fontWeight: 600,
                    color: colors.text,
                    marginBottom: "8px",
                  }}
                >
                  Tips
                </h3>
                <ul
                  style={{
                    fontSize: "14px",
                    color: colors.muted,
                    lineHeight: 1.8,
                    margin: 0,
                    paddingLeft: "18px",
                  }}
                >
                  <li>
                    Lower "Consolidation Tightness" to find more candidates.
                  </li>
                  <li>Lower "MFI Accumulation" if you want earlier signals.</li>
                  <li>
                    Turn off "Sector Momentum" if the overall market is choppy.
                  </li>
                  <li>
                    Scores ≥ 70 with "Active Breakout" signal are the
                    highest-conviction setups.
                  </li>
                </ul>
              </section>
            </div>
          </div>
        </div>
      )}

      {/* Quant Strategy Help Modal */}
      {showQuantHelp && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 100,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            backgroundColor: "rgba(0,0,0,0.6)",
            padding: "24px",
          }}
          onClick={() => setShowQuantHelp(false)}
        >
          <div
            style={{
              maxWidth: "640px",
              width: "100%",
              maxHeight: "80vh",
              overflow: "auto",
              backgroundColor: colors.surface,
              border: `1px solid ${colors.border}`,
              borderRadius: "20px",
              padding: "32px",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: "24px",
              }}
            >
              <h2
                style={{
                  fontSize: "21px",
                  fontWeight: 600,
                  color: colors.text,
                  margin: 0,
                }}
              >
                How Quant Strategy Works
              </h2>
              <button
                onClick={() => setShowQuantHelp(false)}
                style={{
                  width: "32px",
                  height: "32px",
                  borderRadius: "8px",
                  border: "none",
                  backgroundColor: "transparent",
                  color: colors.muted,
                  cursor: "pointer",
                  fontSize: "18px",
                }}
              >
                ×
              </button>
            </div>

            <div
              style={{ display: "flex", flexDirection: "column", gap: "20px" }}
            >
              <section>
                <h3
                  style={{
                    fontSize: "15px",
                    fontWeight: 600,
                    color: colors.text,
                    marginBottom: "8px",
                  }}
                >
                  What is Quant Strategy?
                </h3>
                <p
                  style={{
                    fontSize: "14px",
                    color: colors.muted,
                    lineHeight: 1.6,
                    margin: 0,
                  }}
                >
                  A technical-analysis-first screener that scans the entire S&P
                  1500 using 80+ indicators from the
                  <code
                    style={{
                      backgroundColor: colors.surfaceRaised,
                      padding: "2px 6px",
                      borderRadius: "4px",
                      fontSize: "12px",
                    }}
                  >
                    ta
                  </code>{" "}
                  library. You describe what you want in plain English, the
                  system parses it into precise filters, computes indicators for
                  every stock, and ranks the matches by a hybrid score.
                </p>
              </section>

              <section>
                <h3
                  style={{
                    fontSize: "15px",
                    fontWeight: 600,
                    color: colors.text,
                    marginBottom: "8px",
                  }}
                >
                  Two-Phase Pipeline
                </h3>
                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: "12px",
                  }}
                >
                  {[
                    {
                      name: "1. Parse",
                      desc: "Your natural language prompt is converted into structured filters by a lightweight LLM. You can review and edit every threshold before running the scan.",
                    },
                    {
                      name: "2. Screen",
                      desc: "The backend fetches the requested indicators (plus base scoring fields) for all 1500 stocks, applies your filters, and computes a hybrid 0-100 score for every survivor.",
                    },
                  ].map((step) => (
                    <div
                      key={step.name}
                      style={{
                        padding: "12px",
                        borderRadius: "10px",
                        backgroundColor: colors.surfaceRaised,
                      }}
                    >
                      <div
                        style={{
                          fontSize: "14px",
                          fontWeight: 600,
                          color: colors.text,
                        }}
                      >
                        {step.name}
                      </div>
                      <div
                        style={{
                          fontSize: "13px",
                          color: colors.muted,
                          marginTop: "4px",
                        }}
                      >
                        {step.desc}
                      </div>
                    </div>
                  ))}
                </div>
              </section>

              <section>
                <h3
                  style={{
                    fontSize: "15px",
                    fontWeight: 600,
                    color: colors.text,
                    marginBottom: "8px",
                  }}
                >
                  Hybrid Score (0-100)
                </h3>
                <p
                  style={{
                    fontSize: "14px",
                    color: colors.muted,
                    lineHeight: 1.6,
                    margin: 0,
                  }}
                >
                  Every passing stock gets a score made of two parts. You
                  control the balance between them with the{" "}
                  <strong style={{ color: colors.text }}>Scoring Split</strong>{" "}
                  slider (0%–100%).
                </p>
                <ul
                  style={{
                    fontSize: "14px",
                    color: colors.muted,
                    lineHeight: 1.8,
                    margin: "8px 0 0",
                    paddingLeft: "18px",
                  }}
                >
                  <li>
                    <strong style={{ color: colors.text }}>Base Setup</strong> —
                    Universal setup quality regardless of your filters. Measures
                    trend strength, momentum health, volatility regime, and
                    volume confirmation.
                  </li>
                  <li>
                    <strong style={{ color: colors.text }}>
                      Filter Match Bonus
                    </strong>{" "}
                    — How strongly the stock satisfies your specific filters.
                    The closer an indicator is to your ideal range, the higher
                    the bonus.
                  </li>
                </ul>
                <div
                  style={{
                    marginTop: "12px",
                    padding: "10px",
                    borderRadius: "8px",
                    backgroundColor: colors.surfaceRaised,
                    fontSize: "13px",
                    color: colors.muted,
                    lineHeight: 1.5,
                  }}
                >
                  <strong style={{ color: colors.text }}>
                    Example splits:
                  </strong>
                  <br />
                  <strong>0% Base / 100% Filter</strong> — Rank purely by how
                  well stocks match your exact criteria.
                  <br />
                  <strong>60% Base / 40% Filter</strong> — Balanced: strong
                  setups that also respect your filters (default).
                  <br />
                  <strong>100% Base / 0% Filter</strong> — Rank purely by
                  universal setup quality, ignoring your filters entirely.
                </div>

                <h4
                  style={{
                    fontSize: "14px",
                    fontWeight: 600,
                    color: colors.text,
                    margin: "16px 0 8px",
                  }}
                >
                  Base Setup Breakdown
                </h4>
                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: "12px",
                  }}
                >
                  {/* Trend Strength */}
                  <div
                    style={{
                      padding: "12px",
                      borderRadius: "10px",
                      backgroundColor: colors.surfaceRaised,
                    }}
                  >
                    <div
                      style={{
                        fontSize: "14px",
                        fontWeight: 600,
                        color: colors.text,
                      }}
                    >
                      1. Trend Strength — 30% of total
                    </div>
                    <div
                      style={{
                        fontSize: "13px",
                        color: colors.muted,
                        marginTop: "4px",
                        lineHeight: 1.6,
                      }}
                    >
                      Measures whether the stock is in a healthy, directional
                      uptrend.
                    </div>
                    <ul
                      style={{
                        fontSize: "13px",
                        color: colors.muted,
                        lineHeight: 1.7,
                        margin: "6px 0 0",
                        paddingLeft: "16px",
                      }}
                    >
                      <li>
                        <strong>ADX</strong> (40% of Trend): Linear{" "}
                        <code>ADX × 2</code> capped at 100. ADX=25 → 50 pts.
                        ADX=50 → 100 pts. Below 0 → 0.
                      </li>
                      <li>
                        <strong>SMA Alignment</strong> (35% of Trend):{" "}
                        <code>
                          close {">"} SMA20 {">"} SMA50
                        </code>{" "}
                        = 100 pts. Close above SMA20 only = 70 pts. Close above
                        SMA50 only = 40 pts. Below both = 0.
                      </li>
                      <li>
                        <strong>MACD Diff</strong> (25% of Trend): {">"} 0 = 100
                        pts. ≤ 0 = 0 pts.
                      </li>
                    </ul>
                  </div>

                  {/* Momentum Quality */}
                  <div
                    style={{
                      padding: "12px",
                      borderRadius: "10px",
                      backgroundColor: colors.surfaceRaised,
                    }}
                  >
                    <div
                      style={{
                        fontSize: "14px",
                        fontWeight: 600,
                        color: colors.text,
                      }}
                    >
                      2. Momentum Quality — 25% of total
                    </div>
                    <div
                      style={{
                        fontSize: "13px",
                        color: colors.muted,
                        marginTop: "4px",
                        lineHeight: 1.6,
                      }}
                    >
                      Measures whether momentum is constructive — not
                      overbought, not dead.
                    </div>
                    <ul
                      style={{
                        fontSize: "13px",
                        color: colors.muted,
                        lineHeight: 1.7,
                        margin: "6px 0 0",
                        paddingLeft: "16px",
                      }}
                    >
                      <li>
                        <strong>RSI</strong> (45% of Momentum): Centered at 55.{" "}
                        <code>100 − |RSI − 55| × 2.5</code>, floored at 0.
                        RSI=55 → 100 pts. RSI=30 or 80 → 37.5 pts. Extremes → 0.
                      </li>
                      <li>
                        <strong>ROC</strong> (30% of Momentum):{" "}
                        <code>50 + ROC × 5</code>, clamped 0–100. ROC=0 → 50
                        pts. ROC=+10 → 100 pts. ROC=−10 → 0.
                      </li>
                      <li>
                        <strong>Stochastic</strong> (25% of Momentum): Centered
                        at 50. <code>100 − |Stoch − 50| × 2</code>, floored at
                        0. Stoch=50 → 100 pts. Stoch=0 or 100 → 0.
                      </li>
                    </ul>
                  </div>

                  {/* Volatility Regime */}
                  <div
                    style={{
                      padding: "12px",
                      borderRadius: "10px",
                      backgroundColor: colors.surfaceRaised,
                    }}
                  >
                    <div
                      style={{
                        fontSize: "14px",
                        fontWeight: 600,
                        color: colors.text,
                      }}
                    >
                      3. Volatility Regime — 20% of total
                    </div>
                    <div
                      style={{
                        fontSize: "13px",
                        color: colors.muted,
                        marginTop: "4px",
                        lineHeight: 1.6,
                      }}
                    >
                      Measures “just right” volatility — not too calm, not too
                      wild.
                    </div>
                    <ul
                      style={{
                        fontSize: "13px",
                        color: colors.muted,
                        lineHeight: 1.7,
                        margin: "6px 0 0",
                        paddingLeft: "16px",
                      }}
                    >
                      <li>
                        <strong>ATR %</strong> (50% of Volatility):{" "}
                        <em>Sweet spot 1%–5%</em> = 100 pts. Below 1%: linear{" "}
                        <code>ATR% × 100</code>. 5%–10%: linear decay 100→0.
                        Above 10%: further decay from 50→0.
                      </li>
                      <li>
                        <strong>BB Width</strong> (50% of Volatility):{" "}
                        <em>Sweet spot 2–15</em> = 100 pts. Below 2:{" "}
                        <code>50 + BBW × 25</code>. 15–25: linear decay 100→50.
                        Above 25: further decay from 50 down.
                      </li>
                    </ul>
                  </div>

                  {/* Volume Confirmation */}
                  <div
                    style={{
                      padding: "12px",
                      borderRadius: "10px",
                      backgroundColor: colors.surfaceRaised,
                    }}
                  >
                    <div
                      style={{
                        fontSize: "14px",
                        fontWeight: 600,
                        color: colors.text,
                      }}
                    >
                      4. Volume Confirmation — 25% of total
                    </div>
                    <div
                      style={{
                        fontSize: "13px",
                        color: colors.muted,
                        marginTop: "4px",
                        lineHeight: 1.6,
                      }}
                    >
                      Measures whether money is actually flowing into the stock.
                    </div>
                    <ul
                      style={{
                        fontSize: "13px",
                        color: colors.muted,
                        lineHeight: 1.7,
                        margin: "6px 0 0",
                        paddingLeft: "16px",
                      }}
                    >
                      <li>
                        <strong>Volume Ratio</strong> (50% of Volume): {"<"} 0.5
                        = 20 pts. 0.5–1.0 = 60 pts. 1.0–2.0 = 100 pts. 2.0–5.0 =
                        80 pts. ≥ 5.0 = 60 pts.
                      </li>
                      <li>
                        <strong>MFI</strong> (50% of Volume): ≥ 50 = raw MFI
                        value (55 → 55 pts, 80 → 80 pts). Below 50:{" "}
                        <code>MFI × 2</code> (30 → 60 pts, 20 → 40 pts).
                      </li>
                    </ul>
                  </div>
                </div>

                <p
                  style={{
                    fontSize: "13px",
                    color: colors.muted,
                    lineHeight: 1.6,
                    margin: "12px 0 0",
                  }}
                >
                  <strong>Final formula:</strong> Trend×0.30 + Momentum×0.25 +
                  Volatility×0.20 + Volume×0.25. Result rounded to 1 decimal
                  place.
                </p>
              </section>

              <section>
                <h3
                  style={{
                    fontSize: "15px",
                    fontWeight: 600,
                    color: colors.text,
                    marginBottom: "8px",
                  }}
                >
                  Dynamic Indicators
                </h3>
                <p
                  style={{
                    fontSize: "14px",
                    color: colors.muted,
                    lineHeight: 1.6,
                    margin: 0,
                  }}
                >
                  You are not limited to RSI and moving averages. Mention any
                  indicator the
                  <code
                    style={{
                      backgroundColor: colors.surfaceRaised,
                      padding: "2px 6px",
                      borderRadius: "4px",
                      fontSize: "12px",
                    }}
                  >
                    ta
                  </code>{" "}
                  library supports — e.g. "Stochastic below 20", "ADX above 25",
                  "Bollinger Band Width under 6" — and the screener will compute
                  it on demand with your custom parameters.
                </p>
              </section>

              <section>
                <h3
                  style={{
                    fontSize: "15px",
                    fontWeight: 600,
                    color: colors.text,
                    marginBottom: "8px",
                  }}
                >
                  Tips
                </h3>
                <ul
                  style={{
                    fontSize: "14px",
                    color: colors.muted,
                    lineHeight: 1.8,
                    margin: 0,
                    paddingLeft: "18px",
                  }}
                >
                  <li>
                    Use precise numbers in your prompt for better filter
                    accuracy.
                  </li>
                  <li>
                    Review parsed filters before scanning — you can edit
                    thresholds manually.
                  </li>
                  <li>
                    Adjust the <strong>Scoring Split</strong> slider to control
                    the balance between setup quality and filter match. Slide to
                    0% for pure filter ranking, or 100% for pure setup quality.
                  </li>
                  <li>
                    Scores ≥ 70 usually mean both a strong setup and a good
                    filter match (at default 60/40 split).
                  </li>
                  <li>
                    Enable AI Analysis for a natural-language summary of the top
                    candidates.
                  </li>
                  <li>
                    Use a cutoff date to backtest how the screen would have
                    performed historically.
                  </li>
                </ul>
              </section>
            </div>
          </div>
        </div>
      )}

      {/* Technical Indicator Help Modal */}
      {showIndicatorHelp && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 200,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            backgroundColor: "rgba(0,0,0,0.7)",
            backdropFilter: "blur(4px)",
            padding: "24px",
          }}
          onClick={() => setShowIndicatorHelp(false)}
        >
          <div
            style={{
              maxWidth: "800px",
              width: "100%",
              maxHeight: "85vh",
              overflow: "hidden",
              backgroundColor: colors.surface,
              border: `1px solid ${colors.border}`,
              borderRadius: "24px",
              display: "flex",
              flexDirection: "column",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div
              style={{
                padding: "24px 32px",
                borderBottom: `1px solid ${colors.border}`,
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
              }}
            >
              <div>
                <h2
                  style={{
                    fontSize: "24px",
                    fontWeight: 600,
                    color: colors.text,
                    margin: 0,
                  }}
                >
                  Technical Indicator Guide
                </h2>
                <p
                  style={{
                    fontSize: "14px",
                    color: colors.muted,
                    margin: "4px 0 0",
                  }}
                >
                  80+ indicators from the 'ta' library grouped by category
                </p>
              </div>
              <button
                onClick={() => setShowIndicatorHelp(false)}
                style={{
                  width: "36px",
                  height: "36px",
                  borderRadius: "10px",
                  border: "none",
                  backgroundColor: colors.surfaceRaised,
                  color: colors.text,
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <X style={{ width: "20px", height: "20px" }} />
              </button>
            </div>

            {/* Modal Body */}
            <div style={{ flex: 1, overflowY: "auto", padding: "32px" }}>
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: "32px",
                }}
              >
                {/* Trend Indicators */}
                <section>
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "10px",
                      marginBottom: "16px",
                    }}
                  >
                    <div
                      style={{
                        width: "32px",
                        height: "32px",
                        borderRadius: "8px",
                        backgroundColor: "rgba(59, 130, 246, 0.1)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                      }}
                    >
                      <Zap
                        style={{
                          width: "18px",
                          height: "18px",
                          color: "#3B82F6",
                        }}
                      />
                    </div>
                    <h3
                      style={{
                        fontSize: "18px",
                        fontWeight: 600,
                        color: colors.text,
                        margin: 0,
                      }}
                    >
                      Trend Indicators
                    </h3>
                  </div>
                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns: "1fr 1fr",
                      gap: "12px",
                    }}
                  >
                    {[
                      {
                        name: "SMA (Simple Moving Average)",
                        key: "trend_sma_fast/slow",
                        desc: "The average price over a specific number of periods. SMA 20 is typically used for short-term trend, while SMA 50/200 are for long-term.",
                      },
                      {
                        name: "EMA (Exponential Moving Average)",
                        key: "trend_ema_fast/slow",
                        desc: "Similar to SMA but gives more weight to recent prices, making it more responsive to new information.",
                      },
                      {
                        name: "MACD",
                        key: "trend_macd",
                        desc: "Moving Average Convergence Divergence. Shows the relationship between two moving averages of price. Positive histogram indicates bullish momentum.",
                      },
                      {
                        name: "ADX",
                        key: "trend_adx",
                        desc: "Average Directional Index. Measures the overall strength of a trend. Values above 25 indicate a strong trend.",
                      },
                      {
                        name: "CCI",
                        key: "trend_cci",
                        desc: "Commodity Channel Index. Measures price level relative to an average price level. High values indicate price is well above average.",
                      },
                      {
                        name: "Aroon Indicator",
                        key: "trend_aroon_ind",
                        desc: "Measures the time between highs and lows to identify trend changes and strength.",
                      },
                      {
                        name: "Vortex Indicator",
                        key: "trend_vortex_ind",
                        desc: "Two lines (VI+ and VI-) used to identify the start of a trend and its direction.",
                      },
                      {
                        name: "TRIX",
                        key: "trend_trix",
                        desc: "Triple Exponential Average. Used to filter out price noise and identify trend reversals.",
                      },
                      {
                        name: "Mass Index",
                        key: "trend_mass_index",
                        desc: "Identifies trend reversals by measuring range expansion (the difference between high and low).",
                      },
                      {
                        name: "STC",
                        key: "trend_stc",
                        desc: "Schaff Trend Cycle. Combines MACD with a stochastic cycle for faster, more accurate signals.",
                      },
                    ].map((idx) => (
                      <div
                        key={idx.name}
                        style={{
                          padding: "12px",
                          borderRadius: "12px",
                          backgroundColor: colors.surfaceRaised,
                          border: `1px solid ${colors.border}`,
                        }}
                      >
                        <div
                          style={{
                            fontSize: "14px",
                            fontWeight: 600,
                            color: colors.text,
                          }}
                        >
                          {idx.name}
                        </div>
                        <div
                          style={{
                            fontSize: "11px",
                            color: "#3B82F6",
                            marginTop: "2px",
                            fontFamily: "monospace",
                          }}
                        >
                          {idx.key}
                        </div>
                        <div
                          style={{
                            fontSize: "12px",
                            color: colors.muted,
                            marginTop: "6px",
                            lineHeight: 1.5,
                          }}
                        >
                          {idx.desc}
                        </div>
                      </div>
                    ))}
                  </div>
                </section>

                {/* Momentum Indicators */}
                <section>
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "10px",
                      marginBottom: "16px",
                    }}
                  >
                    <div
                      style={{
                        width: "32px",
                        height: "32px",
                        borderRadius: "8px",
                        backgroundColor: "rgba(16, 185, 129, 0.1)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                      }}
                    >
                      <Sparkles
                        style={{
                          width: "18px",
                          height: "18px",
                          color: "#10B981",
                        }}
                      />
                    </div>
                    <h3
                      style={{
                        fontSize: "18px",
                        fontWeight: 600,
                        color: colors.text,
                        margin: 0,
                      }}
                    >
                      Momentum Indicators
                    </h3>
                  </div>
                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns: "1fr 1fr",
                      gap: "12px",
                    }}
                  >
                    {[
                      {
                        name: "RSI",
                        key: "momentum_rsi",
                        desc: "Relative Strength Index. Measures speed and change of price. >70 is overbought, <30 is oversold.",
                      },
                      {
                        name: "Stochastic Oscillator",
                        key: "momentum_stoch",
                        desc: "Compares a closing price to its price range over time. Used to find reversal points.",
                      },
                      {
                        name: "Williams %R",
                        key: "momentum_wr",
                        desc: "Measures overbought and oversold levels. Similar to Stochastic but on a 0 to -100 scale.",
                      },
                      {
                        name: "Awesome Oscillator",
                        key: "momentum_ao",
                        desc: "Measures market momentum by comparing recent price action to wider price action.",
                      },
                      {
                        name: "KAMA",
                        key: "momentum_kama",
                        desc: "Kaufman Adaptive Moving Average. A moving average that accounts for market noise or volatility.",
                      },
                      {
                        name: "ROC",
                        key: "momentum_roc",
                        desc: "Rate of Change. A pure momentum oscillator that measures the percentage change in price.",
                      },
                      {
                        name: "TSI",
                        key: "momentum_tsi",
                        desc: "True Strength Index. A momentum oscillator that smooths price changes to show the trend.",
                      },
                      {
                        name: "Ultimate Oscillator",
                        key: "momentum_uo",
                        desc: "Uses three different timeframes to capture momentum across short, medium, and long terms.",
                      },
                      {
                        name: "PPO",
                        key: "momentum_ppo",
                        desc: "Percentage Price Oscillator. Shows the relationship between two moving averages in percentage terms.",
                      },
                    ].map((idx) => (
                      <div
                        key={idx.name}
                        style={{
                          padding: "12px",
                          borderRadius: "12px",
                          backgroundColor: colors.surfaceRaised,
                          border: `1px solid ${colors.border}`,
                        }}
                      >
                        <div
                          style={{
                            fontSize: "14px",
                            fontWeight: 600,
                            color: colors.text,
                          }}
                        >
                          {idx.name}
                        </div>
                        <div
                          style={{
                            fontSize: "11px",
                            color: "#10B981",
                            marginTop: "2px",
                            fontFamily: "monospace",
                          }}
                        >
                          {idx.key}
                        </div>
                        <div
                          style={{
                            fontSize: "12px",
                            color: colors.muted,
                            marginTop: "6px",
                            lineHeight: 1.5,
                          }}
                        >
                          {idx.desc}
                        </div>
                      </div>
                    ))}
                  </div>
                </section>

                {/* Volatility Indicators */}
                <section>
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "10px",
                      marginBottom: "16px",
                    }}
                  >
                    <div
                      style={{
                        width: "32px",
                        height: "32px",
                        borderRadius: "8px",
                        backgroundColor: "rgba(168, 85, 247, 0.1)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                      }}
                    >
                      <SlidersHorizontal
                        style={{
                          width: "18px",
                          height: "18px",
                          color: "#A855F7",
                        }}
                      />
                    </div>
                    <h3
                      style={{
                        fontSize: "18px",
                        fontWeight: 600,
                        color: colors.text,
                        margin: 0,
                      }}
                    >
                      Volatility Indicators
                    </h3>
                  </div>
                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns: "1fr 1fr",
                      gap: "12px",
                    }}
                  >
                    {[
                      {
                        name: "Bollinger Bands Width",
                        key: "volatility_bbw",
                        desc: "The width between the upper and lower bands. Low width (squeeze) often precedes a big move.",
                      },
                      {
                        name: "Bollinger Bands %B",
                        key: "volatility_bbp",
                        desc: "Indicates where the current price is relative to the bands (1.0 = upper band, 0 = lower band).",
                      },
                      {
                        name: "ATR",
                        key: "volatility_atr",
                        desc: "Average True Range. Measures the degree of price volatility over a specific period.",
                      },
                      {
                        name: "Keltner Channel Width",
                        key: "volatility_kcw",
                        desc: "Measures volatility using envelopes set above/below an EMA based on ATR.",
                      },
                      {
                        name: "Donchian Channels",
                        key: "volatility_dc",
                        desc: "Formed by the highest high and lowest low over a period. Used to identify breakouts.",
                      },
                      {
                        name: "Ulcer Index",
                        key: "volatility_ui",
                        desc: "Measures downside risk by focusing on the depth and duration of price drawdowns.",
                      },
                    ].map((idx) => (
                      <div
                        key={idx.name}
                        style={{
                          padding: "12px",
                          borderRadius: "12px",
                          backgroundColor: colors.surfaceRaised,
                          border: `1px solid ${colors.border}`,
                        }}
                      >
                        <div
                          style={{
                            fontSize: "14px",
                            fontWeight: 600,
                            color: colors.text,
                          }}
                        >
                          {idx.name}
                        </div>
                        <div
                          style={{
                            fontSize: "11px",
                            color: "#A855F7",
                            marginTop: "2px",
                            fontFamily: "monospace",
                          }}
                        >
                          {idx.key}
                        </div>
                        <div
                          style={{
                            fontSize: "12px",
                            color: colors.muted,
                            marginTop: "6px",
                            lineHeight: 1.5,
                          }}
                        >
                          {idx.desc}
                        </div>
                      </div>
                    ))}
                  </div>
                </section>

                {/* Volume Indicators */}
                <section>
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "10px",
                      marginBottom: "16px",
                    }}
                  >
                    <div
                      style={{
                        width: "32px",
                        height: "32px",
                        borderRadius: "8px",
                        backgroundColor: "rgba(245, 158, 11, 0.1)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                      }}
                    >
                      <BarChart3
                        style={{
                          width: "18px",
                          height: "18px",
                          color: "#F59E0B",
                        }}
                      />
                    </div>
                    <h3
                      style={{
                        fontSize: "18px",
                        fontWeight: 600,
                        color: colors.text,
                        margin: 0,
                      }}
                    >
                      Volume Indicators
                    </h3>
                  </div>
                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns: "1fr 1fr",
                      gap: "12px",
                    }}
                  >
                    {[
                      {
                        name: "OBV",
                        key: "volume_obv",
                        desc: "On-Balance Volume. Uses volume flow to predict price changes. Rising OBV shows accumulation.",
                      },
                      {
                        name: "MFI",
                        key: "volume_mfi",
                        desc: "Money Flow Index. A volume-weighted version of RSI. Measures 'buying power' into the stock.",
                      },
                      {
                        name: "VWAP",
                        key: "volume_vwap",
                        desc: "Volume Weighted Average Price. The average price a stock has traded at, weighted by volume.",
                      },
                      {
                        name: "CMF",
                        key: "volume_cmf",
                        desc: "Chaikin Money Flow. Measures the amount of Money Flow Volume over a specific period.",
                      },
                      {
                        name: "Force Index",
                        key: "volume_fi",
                        desc: "Uses price and volume to measure the power behind a move. High values confirm breakouts.",
                      },
                      {
                        name: "Ease of Movement",
                        key: "volume_em",
                        desc: "Relates price change to volume to show how easily the price can move on low volume.",
                      },
                      {
                        name: "Negative Volume Index",
                        key: "volume_nvi",
                        desc: "Focuses on days when volume decreases, indicating where 'smart money' is positioned.",
                      },
                      {
                        name: "Accumulation/Distribution",
                        key: "volume_adi",
                        desc: "Relates price and volume to show if a stock is being accumulated or distributed.",
                      },
                    ].map((idx) => (
                      <div
                        key={idx.name}
                        style={{
                          padding: "12px",
                          borderRadius: "12px",
                          backgroundColor: colors.surfaceRaised,
                          border: `1px solid ${colors.border}`,
                        }}
                      >
                        <div
                          style={{
                            fontSize: "14px",
                            fontWeight: 600,
                            color: colors.text,
                          }}
                        >
                          {idx.name}
                        </div>
                        <div
                          style={{
                            fontSize: "11px",
                            color: "#F59E0B",
                            marginTop: "2px",
                            fontFamily: "monospace",
                          }}
                        >
                          {idx.key}
                        </div>
                        <div
                          style={{
                            fontSize: "12px",
                            color: colors.muted,
                            marginTop: "6px",
                            lineHeight: 1.5,
                          }}
                        >
                          {idx.desc}
                        </div>
                      </div>
                    ))}
                  </div>
                </section>

                <div
                  style={{
                    padding: "20px",
                    borderRadius: "16px",
                    backgroundColor: "rgba(59, 130, 246, 0.05)",
                    border: "1px dashed rgba(59, 130, 246, 0.3)",
                  }}
                >
                  <div
                    style={{
                      fontSize: "14px",
                      fontWeight: 600,
                      color: colors.text,
                      marginBottom: "8px",
                    }}
                  >
                    Pro Tip: Use Natural Language
                  </div>
                  <p
                    style={{
                      fontSize: "13px",
                      color: colors.muted,
                      margin: 0,
                      lineHeight: 1.6,
                    }}
                  >
                    The Quant Screener understands these keys automatically. You
                    can type things like:
                    <code
                      style={{ color: "#3B82F6", background: "transparent" }}
                    >
                      {" "}
                      "RSI below 30 and SMA 20 above SMA 50"
                    </code>{" "}
                    or
                    <code
                      style={{ color: "#3B82F6", background: "transparent" }}
                    >
                      {" "}
                      "Volume Ratio greater than 2.0 with ADX above 25"
                    </code>
                    .
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Candlestick Chart Modal */}
      <ChartModal
        ticker={chartTicker}
        onClose={closeChart}
        colors={colors}
      />
    </div>
  );
}
