import { useState, useCallback } from "react";
import { TerminalComponent } from "../components/terminal/Terminal";
import { useTheme } from "../context/ThemeContext";

export default function TerminalPage() {
  const { isDarkMode } = useTheme();
  const [sessionId, setSessionId] = useState(() => crypto.randomUUID());
  const [status, setStatus] = useState<"connecting" | "connected" | "disconnected">("connecting");
  const [exitCode, setExitCode] = useState<number | undefined>();

  const handleNewSession = useCallback(() => {
    setSessionId(crypto.randomUUID());
    setStatus("connecting");
    setExitCode(undefined);
  }, []);

  const handleDisconnected = useCallback((code?: number) => {
    setStatus("disconnected");
    setExitCode(code);
  }, []);

  const colors = {
    bg: isDarkMode ? "#050505" : "#f5f5f7",
    surface: isDarkMode ? "#0a0a0a" : "#ffffff",
    text: isDarkMode ? "#ffffff" : "#1d1d1f",
    muted: isDarkMode ? "rgba(255,255,255,0.55)" : "#6e6e73",
    border: isDarkMode ? "rgba(255,255,255,0.08)" : "#d2d2d7",
  };

  const statusColor =
    status === "connected" ? "#10B981"
    : status === "connecting" ? "#F59E0B"
    : "#EF4444";

  const statusLabel =
    status === "connected" ? "Connected"
    : status === "connecting" ? "Connecting..."
    : "Disconnected";

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        backgroundColor: colors.bg,
        color: colors.text,
      }}
    >
      {/* Toolbar */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "8px 16px",
          borderBottom: `1px solid ${colors.border}`,
          backgroundColor: colors.surface,
          flexShrink: 0,
          height: 48,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span style={{ fontWeight: 600, fontSize: 15 }}>AI Terminal</span>
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              fontSize: 12,
              color: colors.muted,
            }}
          >
            <span
              style={{
                width: 8,
                height: 8,
                borderRadius: "50%",
                backgroundColor: statusColor,
                display: "inline-block",
              }}
            />
            {statusLabel}
          </span>
        </div>

        <button
          onClick={handleNewSession}
          style={{
            padding: "6px 14px",
            borderRadius: 6,
            border: `1px solid ${colors.border}`,
            backgroundColor: "transparent",
            color: colors.text,
            fontSize: 13,
            fontWeight: 500,
            cursor: "pointer",
          }}
        >
          New Session
        </button>
      </div>

      {/* Terminal area */}
      <div style={{ flex: 1, padding: 8, overflow: "hidden" }}>
        {status === "disconnected" ? (
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              height: "100%",
              gap: 12,
              color: colors.muted,
            }}
          >
            <span style={{ fontSize: 16 }}>
              Session ended{exitCode != null ? ` (exit code ${exitCode})` : ""}
            </span>
            <button
              onClick={handleNewSession}
              style={{
                padding: "8px 20px",
                borderRadius: 6,
                border: "none",
                backgroundColor: "#10B981",
                color: "#fff",
                fontSize: 14,
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              New Session
            </button>
          </div>
        ) : (
          <TerminalComponent
            sessionId={sessionId}
            onReady={() => setStatus("connected")}
            onDisconnected={handleDisconnected}
          />
        )}
      </div>
    </div>
  );
}
