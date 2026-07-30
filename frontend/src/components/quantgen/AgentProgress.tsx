import { useState, useEffect, useRef, useCallback } from "react";
import {
  Activity,
  CheckCircle2,
  XCircle,
  Clock,
  ChevronDown,
  ChevronRight,
  Sparkles,
  AlertCircle,
  FileCode,
  BarChart3,
  Bug,
  TrendingUp,
  BookOpen,
  Loader2,
  Terminal,
} from "lucide-react";

// ── Types ───────────────────────────────────────────────────────────────────

interface AgentEvent {
  type: string;
  timestamp: string;
  [key: string]: any;
}

interface StepState {
  name: string;
  label: string;
  status: "pending" | "running" | "done" | "failed" | "skipped" | "stopped";
  detail?: string;
  events: AgentEvent[];
}

interface KPI {
  total_return?: number;
  sharpe_ratio?: number;
  max_drawdown?: number;
  win_rate?: number;
  n_trades?: number;
  profit_factor?: number;
}

interface AgentProgressProps {
  sessionId: string | null;
  onComplete?: (code: string, kpis: KPI | null) => void;
  onError?: (error: string) => void;
  isDarkMode: boolean;
}

// ── Step definitions ────────────────────────────────────────────────────────

const STEPS: { name: string; label: string; icon: React.ReactNode }[] = [
  { name: "reading_context", label: "Reading Context", icon: <BookOpen size={16} /> },
  { name: "generating", label: "Generating Code", icon: <FileCode size={16} /> },
  { name: "validating", label: "Validating", icon: <CheckCircle2 size={16} /> },
  { name: "backtesting", label: "Backtesting", icon: <BarChart3 size={16} /> },
  { name: "debugging", label: "Debugging", icon: <Bug size={16} /> },
  { name: "improving", label: "Improving", icon: <TrendingUp size={16} /> },
];

// ── Helpers ─────────────────────────────────────────────────────────────────

function formatTime(isoString: string): string {
  try {
    const d = new Date(isoString);
    return d.toLocaleTimeString("en-US", {
      hour12: false,
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return "--:--:--";
  }
}

function formatPercent(val: number | undefined | null): string {
  if (val == null) return "--";
  return `${(val * 100).toFixed(1)}%`;
}

function formatNumber(val: number | undefined | null, decimals = 2): string {
  if (val == null) return "--";
  return val.toFixed(decimals);
}

function getStatusIcon(status: string, size = 18): React.ReactNode {
  switch (status) {
    case "done":
      return <CheckCircle2 size={size} className="text-emerald-500" />;
    case "running":
      return <Loader2 size={size} className="text-blue-500 animate-spin" />;
    case "failed":
      return <XCircle size={size} className="text-red-500" />;
    case "skipped":
      return <Clock size={size} className="text-yellow-500" />;
    case "stopped":
      return <Clock size={size} className="text-yellow-500" />;
    default:
      return <Clock size={size} className="text-gray-500" />;
  }
}

function getEventIcon(eventType: string, size = 14): React.ReactNode {
  switch (eventType) {
    case "llm_call":
      return <Sparkles size={size} className="text-purple-500" />;
    case "code_generated":
      return <FileCode size={size} className="text-emerald-500" />;
    case "validation":
      return <CheckCircle2 size={size} className="text-blue-500" />;
    case "validation_warning":
      return <AlertCircle size={size} className="text-yellow-500" />;
    case "backtest_result":
      return <BarChart3 size={size} className="text-emerald-500" />;
    case "improvement":
      return <TrendingUp size={size} className="text-purple-500" />;
    case "context":
      return <BookOpen size={size} className="text-blue-500" />;
    case "error_fatal":
      return <XCircle size={size} className="text-red-500" />;
    default:
      return <Terminal size={size} className="text-gray-500" />;
  }
}

// ── Component ──────────────────────────────────────────────────────────────

export default function AgentProgress({
  sessionId,
  onComplete,
  onError,
  isDarkMode,
}: AgentProgressProps) {
  // State
  const [steps, setSteps] = useState<StepState[]>(() =>
    STEPS.map((s) => ({ ...s, status: "pending", events: [] }))
  );
  const [logLines, setLogLines] = useState<
    { time: string; icon: React.ReactNode; text: string; detail?: string }[]
  >([]);
  const [kpis, setKpis] = useState<KPI | null>(null);
  const [finalCode, setFinalCode] = useState<string | null>(null);
  const [isComplete, setIsComplete] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<"timeline" | "log">("timeline");
  const [expandedSteps, setExpandedSteps] = useState<Set<string>>(new Set());
  const [showKpiDetails, setShowKpiDetails] = useState(false);

  const logEndRef = useRef<HTMLDivElement>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  // Auto-scroll log
  useEffect(() => {
    if (viewMode === "log" && logEndRef.current) {
      logEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [logLines, viewMode]);

  // Connect to SSE
  useEffect(() => {
    if (!sessionId) return;

    // Reset state
    setSteps(STEPS.map((s) => ({ ...s, status: "pending", events: [] })));
    setLogLines([]);
    setKpis(null);
    setFinalCode(null);
    setIsComplete(false);
    setError(null);

    const es = new EventSource(`/api/strategy-agent/${sessionId}/stream`);
    eventSourceRef.current = es;

    es.onmessage = (event) => {
      try {
        const data: AgentEvent = JSON.parse(event.data);
        handleEvent(data);
      } catch (e) {
        console.error("Failed to parse SSE event:", e);
      }
    };

    es.onerror = () => {
      // EventSource auto-reconnects, but if it's permanently closed:
      if (es.readyState === EventSource.CLOSED) {
        setError("Connection to agent closed unexpectedly");
        onError?.("Connection to agent closed unexpectedly");
      }
    };

    return () => {
      es.close();
      eventSourceRef.current = null;
    };
  }, [sessionId]);

  // Handle events
  const handleEvent = useCallback(
    (data: AgentEvent) => {
      // Add to log
      const icon = getEventIcon(data.type);
      let text = data.detail || data.type;
      if (data.type === "step") {
        text = `${data.step}: ${data.detail || data.status}`;
      }

      setLogLines((prev) => [
        ...prev,
        { time: formatTime(data.timestamp), icon, text, detail: JSON.stringify(data, null, 2) },
      ]);

      // Handle step events
      if (data.type === "step") {
        setSteps((prev) =>
          prev.map((s) => {
            if (s.name === data.step) {
              return {
                ...s,
                status: data.status || "running",
                detail: data.detail,
                events: [...s.events, data],
              };
            }
            // Mark all previous steps as done if this one is running
            const stepIdx = STEPS.findIndex((st) => st.name === data.step);
            const myIdx = STEPS.findIndex((st) => st.name === s.name);
            if (myIdx < stepIdx && s.status === "pending") {
              return { ...s, status: "done" as const };
            }
            return s;
          })
        );
      }

      // Handle result
      if (data.type === "result") {
        if (data.code) setFinalCode(data.code);
        if (data.kpis) setKpis(data.kpis);
        setIsComplete(true);
        onComplete?.(data.code || "", data.kpis || null);
      }

      // Handle fatal error
      if (data.type === "error_fatal") {
        setError(data.detail || "Unknown error");
        onError?.(data.detail || "Unknown error");
      }

      // Handle backtest results
      if (data.type === "backtest_result" && data.kpis) {
        setKpis(data.kpis);
      }
    },
    [onComplete, onError]
  );

  // Toggle step expansion
  const toggleStep = (name: string) => {
    setExpandedSteps((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  // ── Render ────────────────────────────────────────────────────────────────

  const borderColor = isDarkMode ? "rgba(255,255,255,0.08)" : "#e2e8f0";
  const surfaceColor = isDarkMode ? "rgba(255,255,255,0.03)" : "#f8fafc";
  const textMuted = isDarkMode ? "rgba(255,255,255,0.4)" : "#94a3b8";
  const textSubtle = isDarkMode ? "rgba(255,255,255,0.6)" : "#64748b";

  return (
    <div
      style={{
        borderRadius: "14px",
        border: `1px solid ${borderColor}`,
        backgroundColor: "var(--surface)",
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
        maxHeight: "600px",
      }}
    >
      {/* Header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "12px 16px",
          borderBottom: `1px solid ${borderColor}`,
          backgroundColor: surfaceColor,
          flexShrink: 0,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <Activity size={16} className="text-emerald-500" />
          <span
            style={{
              fontSize: "13px",
              fontWeight: 700,
              letterSpacing: "0.1em",
              textTransform: "uppercase",
              color: "var(--foreground)",
            }}
          >
            AI Strategy Agent
          </span>
          {isComplete && (
            <span
              style={{
                fontSize: "11px",
                fontWeight: 600,
                color: "#10B981",
                padding: "2px 8px",
                borderRadius: "4px",
                backgroundColor: "rgba(16,185,129,0.1)",
              }}
            >
              Complete
            </span>
          )}
          {error && (
            <span
              style={{
                fontSize: "11px",
                fontWeight: 600,
                color: "#EF4444",
                padding: "2px 8px",
                borderRadius: "4px",
                backgroundColor: "rgba(239,68,68,0.1)",
              }}
            >
              Failed
            </span>
          )}
        </div>

        {/* View toggle */}
        <div
          style={{
            display: "flex",
            borderRadius: "6px",
            padding: "2px",
            backgroundColor: isDarkMode ? "rgba(0,0,0,0.3)" : "#e2e8f0",
          }}
        >
          <button
            onClick={() => setViewMode("timeline")}
            style={{
              padding: "4px 10px",
              fontSize: "11px",
              fontWeight: 600,
              borderRadius: "4px",
              border: "none",
              cursor: "pointer",
              backgroundColor:
                viewMode === "timeline" ? "var(--accent)" : "transparent",
              color:
                viewMode === "timeline" ? "#000000" : textMuted,
            }}
          >
            Timeline
          </button>
          <button
            onClick={() => setViewMode("log")}
            style={{
              padding: "4px 10px",
              fontSize: "11px",
              fontWeight: 600,
              borderRadius: "4px",
              border: "none",
              cursor: "pointer",
              backgroundColor:
                viewMode === "log" ? "var(--accent)" : "transparent",
              color: viewMode === "log" ? "#000000" : textMuted,
            }}
          >
            Live Log
          </button>
        </div>
      </div>

      {/* Body */}
      <div
        style={{
          flex: 1,
          overflowY: "auto",
          padding: "12px 16px",
          minHeight: "200px",
        }}
      >
        {viewMode === "timeline" ? (
          /* ── Timeline View ── */
          <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
            {steps.map((step) => (
              <div key={step.name}>
                {/* Step header */}
                <button
                  onClick={() => toggleStep(step.name)}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "10px",
                    width: "100%",
                    padding: "8px 10px",
                    borderRadius: "8px",
                    border: "none",
                    background: "none",
                    cursor: "pointer",
                    color: "var(--foreground)",
                    fontSize: "13px",
                    textAlign: "left",
                    opacity: step.status === "pending" ? 0.5 : 1,
                  }}
                  onMouseEnter={(e) => {
                    if (step.status !== "pending") {
                      e.currentTarget.style.backgroundColor = surfaceColor;
                    }
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.backgroundColor = "transparent";
                  }}
                >
                  {getStatusIcon(step.status)}
                  <span style={{ flex: 1, fontWeight: 600 }}>
                    {step.label}
                  </span>
                  {step.detail && step.status === "running" && (
                    <span
                      style={{
                        fontSize: "11px",
                        color: textSubtle,
                        maxWidth: "200px",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {step.detail}
                    </span>
                  )}
                  {step.events.length > 0 && (
                    <span style={{ color: textMuted, fontSize: "11px" }}>
                      {expandedSteps.has(step.name) ? (
                        <ChevronDown size={14} />
                      ) : (
                        <ChevronRight size={14} />
                      )}
                    </span>
                  )}
                </button>

                {/* Expanded details */}
                {expandedSteps.has(step.name) && (
                  <div
                    style={{
                      marginLeft: "28px",
                      padding: "4px 0 8px 12px",
                      borderLeft: `2px solid ${borderColor}`,
                      display: "flex",
                      flexDirection: "column",
                      gap: "4px",
                    }}
                  >
                    {step.events.map((evt, i) => (
                      <div
                        key={i}
                        style={{
                          display: "flex",
                          alignItems: "flex-start",
                          gap: "8px",
                          padding: "4px 8px",
                          fontSize: "12px",
                          color: textSubtle,
                          lineHeight: 1.5,
                        }}
                      >
                        {getEventIcon(evt.type)}
                        <span style={{ flex: 1 }}>
                          {evt.detail || evt.type}
                        </span>
                        <span
                          style={{
                            fontSize: "10px",
                            color: textMuted,
                            whiteSpace: "nowrap",
                          }}
                        >
                          {formatTime(evt.timestamp)}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}

            {/* KPI Summary */}
            {kpis && (
              <div
                style={{
                  marginTop: "12px",
                  padding: "12px 14px",
                  borderRadius: "10px",
                  backgroundColor: isDarkMode
                    ? "rgba(16,185,129,0.06)"
                    : "rgba(16,185,129,0.04)",
                  border: `1px solid ${
                    isDarkMode
                      ? "rgba(16,185,129,0.12)"
                      : "rgba(16,185,129,0.1)"
                  }`,
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
                      fontSize: "12px",
                      fontWeight: 700,
                      color: "#10B981",
                      display: "flex",
                      alignItems: "center",
                      gap: "6px",
                    }}
                  >
                    <BarChart3 size={14} />
                    Backtest Results
                  </span>
                  <button
                    onClick={() => setShowKpiDetails(!showKpiDetails)}
                    style={{
                      fontSize: "11px",
                      color: textMuted,
                      background: "none",
                      border: "none",
                      cursor: "pointer",
                    }}
                  >
                    {showKpiDetails ? "Hide details" : "Show details"}
                  </button>
                </div>

                {/* Compact KPI row */}
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(auto-fit, minmax(100px, 1fr))",
                    gap: "8px",
                  }}
                >
                  <KpiTile
                    label="Return"
                    value={formatPercent(kpis.total_return)}
                    color={kpis.total_return != null && kpis.total_return >= 0 ? "#10B981" : "#EF4444"}
                  />
                  <KpiTile
                    label="Sharpe"
                    value={formatNumber(kpis.sharpe_ratio)}
                    color={kpis.sharpe_ratio != null && kpis.sharpe_ratio >= 1 ? "#10B981" : kpis.sharpe_ratio != null && kpis.sharpe_ratio >= 0 ? "#F59E0B" : "#EF4444"}
                  />
                  <KpiTile
                    label="Max DD"
                    value={formatPercent(kpis.max_drawdown)}
                    color="#EF4444"
                  />
                  <KpiTile
                    label="Win Rate"
                    value={formatPercent(kpis.win_rate)}
                    color="#3B82F6"
                  />
                  <KpiTile
                    label="Trades"
                    value={formatNumber(kpis.n_trades, 0)}
                    color="#8B5CF6"
                  />
                  <KpiTile
                    label="Profit Factor"
                    value={formatNumber(kpis.profit_factor)}
                    color={kpis.profit_factor != null && kpis.profit_factor >= 1.5 ? "#10B981" : "#F59E0B"}
                  />
                </div>

                {/* Detailed KPI explanation */}
                {showKpiDetails && (
                  <div
                    style={{
                      marginTop: "10px",
                      padding: "10px 12px",
                      borderRadius: "8px",
                      backgroundColor: isDarkMode
                        ? "rgba(0,0,0,0.2)"
                        : "rgba(0,0,0,0.03)",
                      fontSize: "12px",
                      color: textSubtle,
                      lineHeight: 1.6,
                    }}
                  >
                    <p>
                      <strong>Total Return:</strong> The strategy's overall return over the backtest period.
                      {kpis.total_return != null && kpis.total_return >= 0.2
                        ? " Strong positive performance."
                        : kpis.total_return != null && kpis.total_return >= 0
                        ? " Modest positive performance."
                        : " Negative performance — the strategy lost money."}
                    </p>
                    <p>
                      <strong>Sharpe Ratio:</strong> Risk-adjusted return. Above 1.0 is good, above 2.0 is excellent.
                      {kpis.sharpe_ratio != null && kpis.sharpe_ratio >= 1.5
                        ? " Excellent risk-adjusted returns."
                        : kpis.sharpe_ratio != null && kpis.sharpe_ratio >= 0.5
                        ? " Acceptable risk-adjusted returns."
                        : " Low risk-adjusted returns."}
                    </p>
                    <p>
                      <strong>Max Drawdown:</strong> The largest peak-to-trough decline.
                      {kpis.max_drawdown != null && kpis.max_drawdown >= -0.15
                        ? " Manageable drawdown."
                        : " Significant drawdown — consider adding risk controls."}
                    </p>
                    <p>
                      <strong>Win Rate:</strong> Percentage of profitable trades.
                      {kpis.win_rate != null && kpis.win_rate >= 0.5
                        ? " Above 50% — good."
                        : " Below 50% — the strategy relies on larger winners than losers."}
                    </p>
                    <p>
                      <strong>Profit Factor:</strong> Gross profit / gross loss. Above 1.5 is good.
                    </p>
                  </div>
                )}
              </div>
            )}

            {/* Error display */}
            {error && (
              <div
                style={{
                  marginTop: "8px",
                  padding: "10px 14px",
                  borderRadius: "8px",
                  backgroundColor: "rgba(239,68,68,0.08)",
                  border: "1px solid rgba(239,68,68,0.15)",
                  display: "flex",
                  alignItems: "flex-start",
                  gap: "8px",
                  fontSize: "13px",
                  color: "#EF4444",
                  lineHeight: 1.5,
                }}
              >
                <XCircle size={16} style={{ flexShrink: 0, marginTop: "1px" }} />
                <span>{error}</span>
              </div>
            )}
          </div>
        ) : (
          /* ── Live Log View ── */
          <div
            style={{
              fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
              fontSize: "12px",
              lineHeight: 1.6,
            }}
          >
            {logLines.length === 0 ? (
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  height: "150px",
                  color: textMuted,
                  fontSize: "13px",
                  gap: "8px",
                }}
              >
                <Loader2 size={16} className="animate-spin" />
                Waiting for agent to start...
              </div>
            ) : (
              logLines.map((line, i) => (
                <div
                  key={i}
                  style={{
                    display: "flex",
                    gap: "8px",
                    padding: "2px 0",
                    color: textSubtle,
                  }}
                >
                  <span style={{ color: textMuted, flexShrink: 0 }}>
                    {line.time}
                  </span>
                  <span style={{ flexShrink: 0, display: "flex", alignItems: "center" }}>
                    {line.icon}
                  </span>
                  <span style={{ flex: 1 }}>{line.text}</span>
                </div>
              ))
            )}
            <div ref={logEndRef} />
          </div>
        )}
      </div>

      {/* Footer with final code button */}
      {isComplete && finalCode && (
        <div
          style={{
            padding: "10px 16px",
            borderTop: `1px solid ${borderColor}`,
            backgroundColor: surfaceColor,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            flexShrink: 0,
          }}
        >
          <span
            style={{
              fontSize: "12px",
              color: textSubtle,
              display: "flex",
              alignItems: "center",
              gap: "6px",
            }}
          >
            <CheckCircle2 size={14} className="text-emerald-500" />
            Strategy generated — code is loaded in the editor
          </span>
          <span
            style={{
              fontSize: "11px",
              color: textMuted,
            }}
          >
            {finalCode.length / 1024 > 1
              ? `${(finalCode.length / 1024).toFixed(1)}KB`
              : `${finalCode.length} chars`}
          </span>
        </div>
      )}
    </div>
  );
}

// ── KPI Tile Sub-component ──────────────────────────────────────────────────

function KpiTile({
  label,
  value,
  color,
}: {
  label: string;
  value: string;
  color: string;
}) {
  return (
    <div
      style={{
        padding: "6px 10px",
        borderRadius: "6px",
        backgroundColor: "var(--canvas)",
        textAlign: "center",
      }}
    >
      <div
        style={{
          fontSize: "10px",
          fontWeight: 600,
          color: "var(--subtle)",
          textTransform: "uppercase",
          letterSpacing: "0.08em",
          marginBottom: "2px",
        }}
      >
        {label}
      </div>
      <div
        style={{
          fontSize: "16px",
          fontWeight: 700,
          color,
          fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
        }}
      >
        {value}
      </div>
    </div>
  );
}
