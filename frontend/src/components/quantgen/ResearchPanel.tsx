import { useState } from "react";
import { Globe, Bot, RefreshCw, FileText, Info, Sparkles } from "lucide-react";

interface AgentCard {
  name: string;
  content: string;
  color: string;
}

interface ResearchData {
  mode: string;
  agents: AgentCard[];
  compiled_document: string;
}

interface ResearchPanelProps {
  data: ResearchData | null;
  isLoading?: boolean;
  onRegenerate?: (mode: string) => void;
  isDarkMode?: boolean;
}

export default function ResearchPanel({
  data,
  isLoading,
  onRegenerate,
  isDarkMode = true,
}: ResearchPanelProps) {
  const [mode, setMode] = useState<"live" | "simulated">("simulated");

  const handleModeChange = (newMode: "live" | "simulated") => {
    setMode(newMode);
    if (onRegenerate) {
      onRegenerate(newMode);
    }
  };

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
      {/* Header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: "16px",
          flexWrap: "wrap",
          gap: "12px",
        }}
      >
        <div
          style={{
            fontSize: "14px",
            fontWeight: 700,
            color: "var(--foreground)",
            display: "flex",
            alignItems: "center",
            gap: "8px",
          }}
        >
          <FileText size={16} style={{ color: "var(--accent)" }} />
          Research Intelligence
        </div>

        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "8px",
          }}
        >
          {/* Mode Toggle */}
          <div
            style={{
              display: "inline-flex",
              borderRadius: "6px",
              padding: "2px",
              backgroundColor: "var(--canvas)",
            }}
          >
            <button
              onClick={() => handleModeChange("live")}
              style={{
                padding: "6px 12px",
                borderRadius: "4px",
                fontSize: "12px",
                fontWeight: 600,
                border: "none",
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                gap: "4px",
                backgroundColor: mode === "live" ? "var(--accent)" : "transparent",
                color: mode === "live" ? "#000000" : "var(--muted)",
                transition: "all 0.15s ease",
              }}
            >
              <Globe size={12} />
              Live Web
            </button>
            <button
              onClick={() => handleModeChange("simulated")}
              style={{
                padding: "6px 12px",
                borderRadius: "4px",
                fontSize: "12px",
                fontWeight: 600,
                border: "none",
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                gap: "4px",
                backgroundColor: mode === "simulated" ? "var(--accent)" : "transparent",
                color: mode === "simulated" ? "#000000" : "var(--muted)",
                transition: "all 0.15s ease",
              }}
            >
              <Bot size={12} />
              Simulated
            </button>
          </div>

          {/* Mode info tooltip */}
          <div
            title="Simulated uses the LLM's general knowledge to generate plausible research. Live Web uses the LLM's most current knowledge about real-world events. Both may take 2-6 minutes."
            style={{
              display: "flex",
              alignItems: "center",
              cursor: "help",
              color: "var(--subtle)",
            }}
          >
            <Info size={14} />
          </div>

          {onRegenerate && (
            <button
              onClick={() => onRegenerate(mode)}
              disabled={isLoading}
              style={{
                padding: "6px 12px",
                borderRadius: "6px",
                fontSize: "12px",
                fontWeight: 600,
                border: "1px solid var(--border)",
                cursor: isLoading ? "not-allowed" : "pointer",
                backgroundColor: data ? "var(--canvas)" : "var(--accent)",
                color: data ? "var(--foreground)" : "#000000",
                display: "flex",
                alignItems: "center",
                gap: "4px",
                opacity: isLoading ? 0.5 : 1,
                transition: "all 0.15s ease",
              }}
            >
              {isLoading ? (
                <RefreshCw size={12} className="animate-spin" />
              ) : data ? (
                <RefreshCw size={12} />
              ) : (
                <Sparkles size={12} />
              )}
              {data ? "Regenerate" : "Run Research"}
            </button>
          )}
        </div>
      </div>

      {/* Loading State */}
      {isLoading && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px", marginBottom: "16px" }}>
          {Array.from({ length: 4 }).map((_, i) => (
            <div
              key={i}
              style={{
                padding: "16px",
                borderRadius: "10px",
                backgroundColor: isDarkMode ? "rgba(255,255,255,0.03)" : "#f8fafc",
                border: "1px solid var(--border)",
                height: "120px",
              }}
            />
          ))}
        </div>
      )}

      {/* Agent Cards */}
      {!isLoading && data?.agents && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px", marginBottom: "16px" }}>
          {data.agents.map((agent) => (
            <div
              key={agent.name}
              style={{
                padding: "16px",
                borderRadius: "10px",
                backgroundColor: isDarkMode ? "rgba(255,255,255,0.03)" : "#f8fafc",
                border: "1px solid var(--border)",
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                  marginBottom: "12px",
                }}
              >
                <div
                  style={{
                    width: "8px",
                    height: "8px",
                    borderRadius: "50%",
                    backgroundColor: agent.color,
                  }}
                />
                <span
                  style={{
                    fontSize: "12px",
                    fontWeight: 600,
                    color: "var(--muted)",
                  }}
                >
                  {agent.name}
                </span>
              </div>
              <div
                style={{
                  fontSize: "13px",
                  color: "var(--foreground)",
                  lineHeight: 1.6,
                }}
              >
                {agent.content}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* No Data */}
      {!isLoading && !data && (
        <div
          style={{
            textAlign: "center",
            color: "var(--muted)",
            fontSize: "14px",
            padding: "32px 20px",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: "8px",
          }}
        >
          <div style={{ fontSize: "13px", color: "var(--foreground)", fontWeight: 600, marginBottom: "4px" }}>
            Research Intelligence
          </div>
          <div style={{ fontSize: "13px", maxWidth: "480px", lineHeight: 1.6 }}>
            Spawn 4 research agents (Market Sentiment, Competitive Landscape, Risk Factors, Earnings Outlook)
            and compile their findings into an executive summary.
          </div>
          <div style={{ fontSize: "12px", color: "var(--subtle)", marginTop: "4px" }}>
            Note: Analysis takes 2–6 minutes depending on model load.
          </div>
        </div>
      )}

      {/* Compiled Document */}
      {!isLoading && data?.compiled_document && (
        <div
          style={{
            padding: "16px",
            borderRadius: "10px",
            backgroundColor: isDarkMode ? "rgba(255,255,255,0.03)" : "#f8fafc",
            border: "1px solid var(--border)",
          }}
        >
          <div
            style={{
              fontSize: "12px",
              fontWeight: 700,
              color: "var(--foreground)",
              marginBottom: "10px",
              display: "flex",
              alignItems: "center",
              gap: "6px",
            }}
          >
            <FileText size={14} style={{ color: "var(--accent)" }} />
            Compiled Research Document
          </div>
          <div
            style={{
              fontSize: "13px",
              color: "var(--foreground)",
              lineHeight: 1.7,
              backgroundColor: isDarkMode ? "rgba(0,0,0,0.2)" : "#ffffff",
              padding: "14px",
              borderRadius: "8px",
              fontFamily: "Georgia, 'Times New Roman', serif",
            }}
          >
            {data.compiled_document}
          </div>
        </div>
      )}
    </div>
  );
}
