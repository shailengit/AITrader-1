import { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import {
  Search,
  Activity,
  CheckCircle2,
  AlertCircle,
  Loader2,
  TrendingUp,
  BarChart2,
  Sparkles,
  ChevronDown,
  Zap,
  BarChart3,
  SlidersHorizontal,
  Bot,
  Play,
  Cpu,
  Terminal,
  FileDown,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { useTheme } from "../context/ThemeContext";

interface ScanResult {
  ticker: string;
  signal?: string;
  fundamental_catalyst?: string;
  close?: number;
  data_date?: string;
  sma_20?: number;
  sma_50?: number;
  rsi?: number;
  macd?: number;
  volume?: number;
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

export default function StockScreener() {
  const navigate = useNavigate();
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
  const [showTerminal, setShowTerminal] = useState(true);
  const [progress, setProgress] = useState(0);
  const logsEndRef = useRef<HTMLDivElement>(null);
  const [filters, setFilters] = useState({
    squeeze_threshold: 1.15,
    accumulation_threshold: 0.005,
    volume_threshold: 1.5,
  });

  // Theme-aware colors
  const colors = {
    text: isDarkMode ? '#FAFAFA' : '#1d1d1f',
    muted: isDarkMode ? '#A1A1AA' : '#6e6e73',
    subtle: isDarkMode ? '#52525B' : '#86868b',
    surface: isDarkMode ? '#27272A' : '#ffffff',
    surfaceAlt: isDarkMode ? '#27272A' : '#f5f5f7',
    border: isDarkMode ? '#3F3F46' : '#d2d2d7',
    borderLight: isDarkMode ? '#27272A' : '#e5e5e7',
    inputBg: isDarkMode ? 'rgba(0, 0, 0, 0.5)' : '#ffffff',
    canvas: isDarkMode ? '#000000' : '#f5f5f7',
  };

  useEffect(() => {
    fetch("/api/screener/modes")
      .then((res) => res.json())
      .then((data) => setModes(data.modes))
      .catch((err) => console.error("Failed to fetch modes:", err));
  }, []);

  // Auto-scroll terminal to bottom
  useEffect(() => {
    if (logsEndRef.current && showTerminal) {
      logsEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs, showTerminal]);

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
          filters: selectedMode === "dormant_giant" ? filters : undefined,
        }),
      });

      if (!res.ok) throw new Error("Failed to start scan");

      const data = await res.json();
      const scanId = data.scan_id;

      // Set up SSE connection
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
        console.warn("SSE connection error, falling back to polling");
        eventSource.close();
        pollScanStatusFallback(scanId);
      };

      // Set initial scan status
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
      } catch (err) {
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

  const getLogColor = (color: string) => {
    switch (color) {
      case "blue": return isDarkMode ? "#60A5FA" : "#2563EB";
      case "green": return isDarkMode ? "#34D399" : "#059669";
      case "amber": return isDarkMode ? "#FBBF24" : "#D97706";
      case "purple": return isDarkMode ? "#A78BFA" : "#7C3AED";
      case "red": return "#EF4444";
      default: return isDarkMode ? "#A1A1AA" : "#6e6e73";
    }
  };

  const selectedModeInfo = modes.find((m) => m.id === selectedMode);

  return (
    <div className="min-h-screen bg-canvas flex flex-col">
      {/* Background Effects - Only in dark mode */}
      {isDarkMode && (
        <div className="fixed inset-0 overflow-hidden pointer-events-none">
          <div
            className="absolute inset-0"
            style={{
              background: 'linear-gradient(to bottom, rgba(16, 185, 129, 0.03), transparent, transparent)'
            }}
          />
          <div
            className="absolute top-20 left-1/4 w-64 h-64 rounded-full blur-[100px] opacity-20 animate-float"
            style={{ background: 'rgba(16, 185, 129, 0.15)' }}
          />
          <div
            className="absolute top-40 right-1/4 w-48 h-48 rounded-full blur-[100px] opacity-15 animate-float"
            style={{
              background: 'rgba(59, 130, 246, 0.1)',
              animationDelay: '2s'
            }}
          />
          <div
            className="absolute top-60 right-1/3 w-32 h-32 rounded-full blur-[80px] opacity-10"
            style={{ background: 'rgba(16, 185, 129, 0.1)' }}
          />
        </div>
      )}

      {/* Hero Section */}
      <div className="relative z-10 w-full flex justify-center pt-32 pb-16 px-8">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
          className="max-w-5xl mx-auto text-center"
        >
          <div className="flex justify-center mb-8">
            <div
              className="flex items-center justify-center gap-2 rounded-full px-5 py-2.5 border"
              style={{
                background: isDarkMode ? 'rgba(16, 185, 129, 0.1)' : 'rgba(16, 185, 129, 0.08)',
                borderColor: isDarkMode ? 'rgba(16, 185, 129, 0.2)' : 'rgba(16, 185, 129, 0.3)'
              }}
            >
              <Sparkles className="w-5 h-5 text-emerald-500" />
              <span className="text-base text-emerald-600 font-medium">
                Multi-Agent Intelligence
              </span>
            </div>
          </div>

          <h1
            className="text-7xl font-bold mb-6 tracking-tight text-center"
            style={{
              color: colors.text,
              letterSpacing: '-0.04em'
            }}
          >
            AI Stock Screener
          </h1>

          <p
            className="text-2xl max-w-3xl mx-auto leading-relaxed text-center"
            style={{ color: colors.muted }}
          >
            Advanced technical and fundamental analysis powered by intelligent
            agents
          </p>
        </motion.div>
      </div>

      {/* Configuration Section */}
      <div className="relative z-10 w-full flex justify-center px-8 py-10 pb-20">
        <div style={{ maxWidth: 1600, width: '100%', margin: '0 auto' }}>
          {/* Mode Selection */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.1 }}
            className="mb-10"
          >
            <div className="flex flex-col items-center text-center gap-4 mb-8">
              <div
                className="w-14 h-14 rounded-2xl flex items-center justify-center"
                style={{ background: isDarkMode ? 'rgba(16, 185, 129, 0.1)' : 'rgba(16, 185, 129, 0.08)' }}
              >
                <Play className="w-7 h-7 text-emerald-500" />
              </div>
              <div>
                <h2 className="text-3xl font-bold text-center" style={{ color: colors.text }}>
                  Select Mode
                </h2>
                <p className="text-base mt-1 text-center" style={{ color: colors.muted }}>
                  Choose your screening strategy
                </p>
              </div>
            </div>

            <div className="grid lg:grid-cols-2 gap-8">
              {modes.map((mode) => {
                const isSelected = selectedMode === mode.id;
                const Icon = mode.id === "dormant_giant" ? Zap : BarChart3;

                return (
                  <button
                    key={mode.id}
                    onClick={() => setSelectedMode(mode.id)}
                    className={`relative p-8 rounded-3xl text-center transition-all duration-300 border ${
                      isSelected
                        ? isDarkMode
                          ? "border-emerald-500/50 shadow-glow"
                          : "border-emerald-500 shadow-lg"
                        : isDarkMode
                          ? "hover:border-zinc-700"
                          : "hover:border-zinc-300"
                    }`}
                    style={{
                      backgroundColor: isSelected
                        ? isDarkMode ? colors.surface : '#ffffff'
                        : isDarkMode ? 'rgba(39, 39, 42, 0.5)' : '#f5f5f7',
                      borderColor: isSelected
                        ? 'rgba(16, 185, 129, 0.5)'
                        : isDarkMode ? '#3F3F46' : '#d2d2d7'
                    }}
                  >
                    <div className="flex flex-col items-center gap-6">
                      <div
                        className={`w-16 h-16 rounded-2xl flex items-center justify-center shrink-0`}
                        style={{
                          backgroundColor: isSelected
                            ? isDarkMode ? 'rgba(16, 185, 129, 0.1)' : 'rgba(16, 185, 129, 0.08)'
                            : isDarkMode ? 'rgba(63, 63, 70, 0.5)' : '#e5e5e7'
                        }}
                      >
                        <Icon
                          className={`w-8 h-8 ${isSelected ? "text-emerald-500" : isDarkMode ? "text-zinc-500" : "text-zinc-400"}`}
                        />
                      </div>

                      <div className="w-full">
                        <div className="flex items-center justify-center gap-2 mb-2">
                          <h3 className={`text-2xl font-bold text-center ${isSelected ? "" : isDarkMode ? "text-zinc-300" : "text-zinc-600"}`}
                            style={{ color: isSelected ? colors.text : undefined }}
                          >
                            {mode.name}
                          </h3>
                          {isSelected && (
                            <div className="w-6 h-6 rounded-full bg-emerald-500 flex items-center justify-center">
                              <div className="w-2.5 h-2.5 rounded-full bg-white" />
                            </div>
                          )}
                        </div>

                        <p className="text-base leading-relaxed mb-4 text-center" style={{ color: colors.muted }}>
                          {mode.description}
                        </p>

                        <div className="flex flex-wrap justify-center gap-2">
                          {mode.agents.slice(0, 4).map((agent) => (
                            <span
                              key={agent}
                              className={`text-sm px-3 py-1.5 rounded-full font-medium`}
                              style={{
                                backgroundColor: isSelected
                                  ? isDarkMode ? 'rgba(16, 185, 129, 0.1)' : 'rgba(16, 185, 129, 0.08)'
                                  : isDarkMode ? '#27272A' : '#e5e5e7',
                                color: isSelected ? '#10B981' : isDarkMode ? '#A1A1AA' : '#6e6e73',
                                border: isSelected ? `1px solid ${isDarkMode ? 'rgba(16, 185, 129, 0.2)' : 'rgba(16, 185, 129, 0.3)'}` : 'none'
                              }}
                            >
                              {agent}
                            </span>
                          ))}
                        </div>
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          </motion.div>

          {/* Settings Grid */}
          <div className="grid xl:grid-cols-3 gap-8 mt-16">
            {/* AI Analysis */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.2 }}
              className="xl:col-span-2 rounded-3xl p-8"
              style={{
                backgroundColor: colors.surface,
                border: `1px solid ${colors.border}`
              }}
            >
              <div className="flex flex-col items-center text-center mb-8">
                <div className="flex items-center gap-4 mb-2">
                  <div
                    className="w-14 h-14 rounded-2xl flex items-center justify-center"
                    style={{ background: isDarkMode ? 'rgba(16, 185, 129, 0.1)' : 'rgba(16, 185, 129, 0.08)' }}
                  >
                    <Bot className="w-7 h-7 text-emerald-500" />
                  </div>
                  <div>
                    <h3 className="text-2xl font-bold text-center" style={{ color: colors.text }}>
                      AI Analysis
                    </h3>
                  </div>
                </div>
                <p className="text-base text-center" style={{ color: colors.muted }}>
                  Multi-agent interpretation for deeper insights
                </p>

                <button
                  type="button"
                  role="switch"
                  aria-checked={useAi}
                  onClick={() => setUseAi(!useAi)}
                  className={`relative w-16 h-9 rounded-full transition-colors mt-4 ${
                    useAi ? "bg-emerald-500" : isDarkMode ? "bg-zinc-700" : "bg-zinc-300"
                  }`}
                >
                  <div
                    className={`absolute top-1 w-7 h-7 rounded-full transition-transform ${
                      useAi ? "translate-x-8" : "translate-x-1"
                    }`}
                    style={{ backgroundColor: isDarkMode ? '#000000' : '#ffffff' }}
                  />
                </button>
              </div>

              {useAi && (
                <div
                  className="rounded-2xl p-6"
                  style={{
                    backgroundColor: isDarkMode ? 'rgba(0, 0, 0, 0.5)' : '#f5f5f7',
                    border: `1px solid ${colors.border}`
                  }}
                >
                  <label className="block text-sm font-semibold uppercase tracking-wide mb-3 text-center" style={{ color: colors.muted }}>
                    Custom Instructions
                  </label>
                  <textarea
                    value={customPrompt}
                    onChange={(e) => setCustomPrompt(e.target.value)}
                    placeholder={
                      selectedMode === "dormant_giant"
                        ? "Begin the daily Dormant Giant screening workflow..."
                        : "Find me candidates for a high-growth breakout. Technically, they should be in a Volatility Squeeze (volatility_bbw). Fundamentally, they must have positive QoQ revenue growth."
                    }
                    className="w-full h-32 border rounded-xl p-4 text-lg focus:ring-2 focus:ring-emerald-500/50 focus:border-emerald-500/50 outline-none resize-none"
                    style={{
                      backgroundColor: colors.inputBg,
                      borderColor: colors.border,
                      color: colors.text
                    }}
                  />
                </div>
              )}

              {/* Progress Bar */}
              {(isScanning || scanStatus?.status === "completed") && (
                <div
                  className="mt-6 p-6 rounded-2xl"
                  style={{
                    backgroundColor: isDarkMode ? 'rgba(0, 0, 0, 0.5)' : '#f5f5f7',
                    border: `1px solid ${colors.border}`
                  }}
                >
                  <div className="flex justify-between text-base mb-3">
                    <span style={{ color: colors.muted }}>
                      {scanStatus?.status === "completed" ? "Analysis complete" : "Analyzing stocks"}
                    </span>
                    <span className="font-bold" style={{ color: colors.text }}>{progress}%</span>
                  </div>
                  <div
                    className="w-full h-3 rounded-full overflow-hidden"
                    style={{ backgroundColor: isDarkMode ? '#27272A' : '#e5e5e7' }}
                  >
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${progress}%` }}
                      transition={{ duration: 0.5, ease: "easeOut" }}
                      className="h-full rounded-full bg-emerald-500"
                    />
                  </div>
                </div>
              )}

              {/* Live Terminal — persists after scan so user can review logs */}
              {logs.length > 0 && (
                <div
                  className="mt-6 rounded-2xl overflow-hidden"
                  style={{
                    backgroundColor: isDarkMode ? '#000000' : '#1e1e1e',
                    border: `1px solid ${colors.border}`
                  }}
                >
                  <button
                    onClick={() => setShowTerminal(!showTerminal)}
                    className="w-full flex items-center justify-between px-6 py-3"
                    style={{ backgroundColor: isDarkMode ? '#18181b' : '#2d2d2d' }}
                  >
                    <div className="flex items-center gap-2">
                      <Terminal className="w-4 h-4 text-emerald-500" />
                      <span className="text-sm font-medium text-white">
                        Agent Terminal {scanStatus?.status === "completed" ? "— Complete" : scanStatus?.status === "failed" ? "— Failed" : ""}
                      </span>
                      <span className="text-xs text-zinc-400">({logs.length} events)</span>
                      {isScanning && (
                        <span className="flex h-2 w-2 relative">
                          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                          <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                        </span>
                      )}
                    </div>
                    <ChevronDown
                      className={`w-4 h-4 text-zinc-400 transition-transform ${showTerminal ? "rotate-180" : ""}`}
                    />
                  </button>

                  <AnimatePresence>
                    {showTerminal && (
                      <motion.div
                        initial={{ height: 0 }}
                        animate={{ height: 320 }}
                        exit={{ height: 0 }}
                        className="overflow-y-auto"
                        style={{ maxHeight: 320 }}
                      >
                        <div className="p-4 space-y-1 font-mono text-xs">
                          {logs.map((log, i) => (
                            <div key={i} className="flex items-start gap-2">
                              <span
                                className="shrink-0 font-bold"
                                style={{ color: getLogColor(log.color) }}
                              >
                                [{log.agent}]
                              </span>
                              <span className="text-zinc-300 whitespace-pre-wrap">
                                {log.message}
                              </span>
                            </div>
                          ))}
                          <div ref={logsEndRef} />
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              )}
            </motion.div>

            {/* Filters Sidebar */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.3 }}
              className="space-y-6"
            >
              {selectedMode === "dormant_giant" && (
                <div
                  className="rounded-3xl p-8"
                  style={{
                    backgroundColor: colors.surface,
                    border: `1px solid ${colors.border}`
                  }}
                >
                  <div className="flex flex-col items-center text-center gap-4 mb-8">
                    <div
                      className="w-14 h-14 rounded-2xl flex items-center justify-center"
                      style={{ backgroundColor: isDarkMode ? 'rgba(63, 63, 70, 0.5)' : '#e5e5e7' }}
                    >
                      <SlidersHorizontal className={`w-7 h-7 ${isDarkMode ? 'text-zinc-400' : 'text-zinc-500'}`} />
                    </div>
                    <div>
                      <h3 className="text-xl font-bold text-center" style={{ color: colors.text }}>
                        Sensitivity
                      </h3>
                      <p className="text-sm text-center" style={{ color: colors.muted }}>
                        Adjust thresholds
                      </p>
                    </div>
                  </div>

                  <div className="space-y-8">
                    {[
                      {
                        key: "squeeze_threshold",
                        label: "Squeeze",
                        min: 1,
                        max: 2,
                        step: 0.01,
                      },
                      {
                        key: "accumulation_threshold",
                        label: "Accumulation",
                        min: 0.001,
                        max: 0.02,
                        step: 0.001,
                      },
                      {
                        key: "volume_threshold",
                        label: "Volume",
                        min: 1,
                        max: 3,
                        step: 0.1,
                      },
                    ].map((slider) => (
                      <div key={slider.key}>
                        <div className="flex justify-between items-center mb-3">
                          <span className="text-base font-medium text-center" style={{ color: colors.text }}>
                            {slider.label}
                          </span>
                          <span className="text-base font-bold" style={{ color: colors.text }}>
                            {filters[slider.key as keyof typeof filters]}
                          </span>
                        </div>
                        <input
                          type="range"
                          min={slider.min}
                          max={slider.max}
                          step={slider.step}
                          value={filters[slider.key as keyof typeof filters]}
                          onChange={(e) =>
                            setFilters({
                              ...filters,
                              [slider.key]: parseFloat(e.target.value),
                            })
                          }
                          className="w-full h-2.5 rounded-full appearance-none cursor-pointer"
                          style={{
                            backgroundColor: isDarkMode ? '#27272A' : '#e5e5e7',
                            accentColor: '#10B981'
                          }}
                        />
                        <div
                          className="flex justify-between mt-2 text-xs"
                          style={{ color: colors.muted }}
                        >
                          <span>{slider.min}</span>
                          <span>{slider.max}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {selectedMode === "quant_strategy" &&
                selectedModeInfo?.supports_backtesting && (
                  <div
                    className="rounded-3xl p-8"
                    style={{
                      backgroundColor: colors.surface,
                      border: `1px solid ${colors.border}`
                    }}
                  >
                    <label className="block text-sm font-semibold uppercase tracking-wide mb-3" style={{ color: colors.muted }}>
                      Backtest Cutoff Date
                    </label>
                    <input
                      type="date"
                      value={cutoffDate}
                      onChange={(e) => setCutoffDate(e.target.value)}
                      className="w-full border rounded-xl px-4 py-3 text-lg focus:ring-2 focus:ring-emerald-500/50 focus:border-emerald-500/50 outline-none"
                      style={{
                        backgroundColor: isDarkMode ? 'rgba(0, 0, 0, 0.5)' : '#ffffff',
                        borderColor: colors.border,
                        color: colors.text
                      }}
                    />
                  </div>
                )}

              <button
                onClick={startScan}
                disabled={isScanning}
                className={`w-full py-5 px-8 rounded-2xl text-lg font-bold transition-all flex items-center justify-center gap-3 ${
                  isScanning
                    ? isDarkMode ? "bg-zinc-800 text-zinc-500" : "bg-zinc-200 text-zinc-400"
                    : "bg-emerald-500 text-white hover:bg-emerald-600"
                }`}
              >
                {isScanning ? (
                  <>
                    <Loader2 className="w-6 h-6 animate-spin" />
                    <span>Scanning...</span>
                  </>
                ) : (
                  <>
                    <Activity className="w-6 h-6" />
                    <span>Start {useAi ? "AI " : ""}Screen</span>
                  </>
                )}
              </button>

              {/* PDF Download */}
              {scanStatus?.status === "completed" && (
                <motion.button
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  onClick={downloadPDF}
                  className="w-full py-4 px-8 rounded-2xl text-lg font-bold transition-all flex items-center justify-center gap-3 border-2"
                  style={{
                    borderColor: isDarkMode ? 'rgba(16, 185, 129, 0.5)' : 'rgba(16, 185, 129, 0.7)',
                    color: isDarkMode ? '#34d399' : '#059669',
                    backgroundColor: isDarkMode ? 'rgba(16, 185, 129, 0.1)' : 'rgba(16, 185, 129, 0.08)'
                  }}
                >
                  <FileDown className="w-6 h-6" />
                  <span>Download PDF Report</span>
                </motion.button>
              )}
            </motion.div>
          </div>

          {/* Empty State */}
          {!scanStatus && !isScanning && results.length === 0 && !error && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.5 }}
              className="mt-20 text-center pb-8"
            >
              <div
                className="w-24 h-24 rounded-full flex items-center justify-center mx-auto mb-6"
                style={{ backgroundColor: isDarkMode ? 'rgba(39, 39, 42, 0.5)' : '#f5f5f7' }}
              >
                <Search className="w-12 h-12" style={{ color: isDarkMode ? '#52525B' : '#9ca3af' }} />
              </div>
              <p className="text-2xl font-bold mb-2" style={{ color: colors.text }}>
                Ready to scan
              </p>
              <p className="text-lg" style={{ color: colors.muted }}>
                Configure settings and click Start to begin analysis
              </p>
            </motion.div>
          )}
        </div>
      </div>

      {/* Results Section */}
      {(results.length > 0 || aiReport) && (
        <div
          className="relative z-10 w-full flex justify-center py-20 border-t"
          style={{
            backgroundColor: isDarkMode ? 'rgba(0, 0, 0, 0.5)' : '#f5f5f7',
            borderColor: colors.border
          }}
        >
          <div style={{ maxWidth: 1600, width: '100%', margin: '0 auto', padding: '0 32px' }}>
            {/* AI Report */}
            <AnimatePresence>
              {aiReport && (
                <motion.div
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -20 }}
                  className="mb-12"
                >
                  <div
                    className="rounded-3xl p-8"
                    style={{
                      backgroundColor: colors.surface,
                      border: `1px solid ${colors.border}`
                    }}
                  >
                    <div className="flex flex-col items-center text-center mb-6">
                      <div className="flex items-center gap-4 mb-2">
                        <div
                          className="w-14 h-14 rounded-2xl flex items-center justify-center"
                          style={{ background: isDarkMode ? 'rgba(16, 185, 129, 0.1)' : 'rgba(16, 185, 129, 0.08)' }}
                        >
                          <Cpu className="w-7 h-7 text-emerald-500" />
                        </div>
                        <div>
                          <h2 className="text-2xl font-bold text-center" style={{ color: colors.text }}>
                            AI Analysis Report
                          </h2>
                        </div>
                      </div>
                      <p className="text-base text-center" style={{ color: colors.muted }}>
                        Generated by multi-agent team
                      </p>
                      <button
                        onClick={() => setShowReport(!showReport)}
                        className="flex items-center justify-center gap-2 text-base px-4 py-2 mx-auto mt-4 hover:text-emerald-600"
                        style={{ color: isDarkMode ? '#34d399' : '#059669' }}
                      >
                        {showReport ? "Hide" : "Show"}
                        <ChevronDown
                          className={`w-5 h-5 transition-transform ${showReport ? "rotate-180" : ""}`}
                        />
                      </button>
                    </div>

                    <AnimatePresence>
                      {showReport && (
                        <motion.div
                          initial={{ height: 0, opacity: 0 }}
                          animate={{ height: "auto", opacity: 1 }}
                          exit={{ height: 0, opacity: 0 }}
                          className="overflow-hidden"
                        >
                          <div
                            className="rounded-2xl p-6 border"
                            style={{
                              backgroundColor: isDarkMode ? 'rgba(0, 0, 0, 0.5)' : '#ffffff',
                              borderColor: colors.border
                            }}
                          >
                            <pre
                              className="whitespace-pre-wrap text-base font-mono leading-relaxed"
                              style={{ color: colors.muted }}
                            >
                              {aiReport}
                            </pre>
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            {/* Results Grid */}
            <AnimatePresence>
              {results.length > 0 && (
                <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                  <div className="flex flex-col items-center text-center mb-8">
                    <h2 className="text-3xl font-bold text-center mb-4" style={{ color: colors.text }}>
                      {results.length} stocks found
                    </h2>
                    <div className="flex items-center gap-2" style={{ color: isDarkMode ? '#34d399' : '#059669' }}>
                      <CheckCircle2 className="w-6 h-6" />
                      <span className="text-base font-medium">
                        Analysis complete
                      </span>
                    </div>
                  </div>

                  <div className="grid md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 gap-6">
                    {results.map((result, index) => (
                      <motion.div
                        key={result.ticker}
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: index * 0.05 }}
                        className="rounded-3xl p-6 transition-colors text-center cursor-pointer"
                        style={{
                          backgroundColor: colors.surface,
                          border: `1px solid ${colors.border}`,
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.borderColor = isDarkMode ? 'rgba(16, 185, 129, 0.3)' : 'rgba(16, 185, 129, 0.5)';
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.borderColor = colors.border;
                        }}
                        onClick={() => navigate(`/quantgen/build?ticker=${result.ticker}`)}
                      >
                        <div className="flex flex-col items-center mb-4">
                          <div>
                            <h3 className="text-2xl font-bold text-center" style={{ color: colors.text }}>
                              {result.ticker}
                            </h3>
                            {result.signal && (
                              <span
                                className="text-base text-center block"
                                style={{ color: isDarkMode ? '#34d399' : '#059669' }}
                              >
                                {result.signal}
                              </span>
                            )}
                          </div>
                          <TrendingUp className="w-6 h-6 mt-2" style={{ color: colors.muted }} />
                        </div>

                        {result.close && (
                          <p className="text-3xl font-bold mb-4 text-center" style={{ color: colors.text }}>
                            ${result.close.toFixed(2)}
                          </p>
                        )}

                        {result.fundamental_catalyst && (
                          <div
                            className="mb-4 p-4 rounded-xl border"
                            style={{
                              background: isDarkMode ? 'rgba(16, 185, 129, 0.05)' : 'rgba(16, 185, 129, 0.08)',
                              borderColor: isDarkMode ? 'rgba(16, 185, 129, 0.2)' : 'rgba(16, 185, 129, 0.3)'
                            }}
                          >
                            <p
                              className="text-base text-center"
                              style={{ color: isDarkMode ? '#34d399' : '#059669' }}
                            >
                              {result.fundamental_catalyst}
                            </p>
                          </div>
                        )}

                        {(result.sma_20 || result.rsi) && (
                          <div className="grid grid-cols-2 gap-4 text-base">
                            {result.sma_20 && (
                              <div style={{ color: colors.muted }}>
                                <span className="block text-sm mb-1 text-center" style={{ color: isDarkMode ? '#52525B' : '#9ca3af' }}>
                                  SMA(20)
                                </span>
                                <span className="font-bold text-center block" style={{ color: colors.text }}>
                                  {result.sma_20.toFixed(2)}
                                </span>
                              </div>
                            )}
                            {result.rsi && (
                              <div style={{ color: colors.muted }}>
                                <span className="block text-sm mb-1 text-center" style={{ color: isDarkMode ? '#52525B' : '#9ca3af' }}>
                                  RSI
                                </span>
                                <span className="font-bold text-center block" style={{ color: colors.text }}>
                                  {result.rsi.toFixed(1)}
                                </span>
                              </div>
                            )}
                          </div>
                        )}

                        <div
                          className="mt-4 pt-4 flex items-center justify-center gap-2 text-sm"
                          style={{
                            color: colors.muted,
                            borderTop: `1px solid ${colors.border}`
                          }}
                        >
                          <BarChart2 className="w-5 h-5" />
                          <span>Technical + Fundamental</span>
                        </div>
                      </motion.div>
                    ))}
                    {/* Hint about clicking cards */}
                    {results.length > 0 && (
                      <div className="col-span-full text-center mt-4">
                        <p className="text-sm" style={{ color: colors.muted }}>
                          Click any stock card to open it in QuantGen Strategy Builder
                        </p>
                      </div>
                    )}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
      )}

      {/* Error Toast */}
      <AnimatePresence>
        {error && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="fixed bottom-8 left-1/2 -translate-x-1/2 bg-red-500 text-white px-8 py-4 rounded-2xl shadow-2xl flex items-center gap-3 z-50 text-lg font-medium"
          >
            <AlertCircle className="w-6 h-6" />
            <span>{error}</span>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
