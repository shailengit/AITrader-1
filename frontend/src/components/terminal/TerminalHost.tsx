import { useEffect, useRef, useState, useCallback } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Terminal } from "xterm";
import { FitAddon } from "xterm-addon-fit";
import "xterm/css/xterm.css";
import { FloatingPanel, type PanelState } from "./FloatingPanel";
import { useTheme } from "../../context/ThemeContext";

const WS_BASE = (() => {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/api/terminal/ws`;
})();

const MAX_AUTO_RECONNECTS = 8;
const RECONNECT_BASE_DELAY_MS = 250;
const RECONNECT_MAX_DELAY_MS = 4000;

const STORAGE_KEY_SESSION = "terminal_session_id";
const STORAGE_KEY_PANEL = "terminal_panel_state";

function defaultPanelState(): PanelState {
  return {
    x: Math.max(0, window.innerWidth - 620),
    y: Math.max(0, window.innerHeight - 420),
    width: 600,
    height: 400,
    minimized: false,
  };
}

function loadPanelState(): PanelState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY_PANEL);
    if (!raw) return defaultPanelState();
    const parsed = JSON.parse(raw) as Partial<PanelState>;
    return {
      x: Number(parsed.x) || 0,
      y: Number(parsed.y) || 0,
      width: Number(parsed.width) || 600,
      height: Number(parsed.height) || 400,
      minimized: Boolean(parsed.minimized),
    };
  } catch {
    return defaultPanelState();
  }
}

export function TerminalHost() {
  const { isDarkMode } = useTheme();
  const location = useLocation();
  const navigate = useNavigate();
  const mode: "fullpage" | "floating" =
    location.pathname === "/terminal" ? "fullpage" : "floating";

  // === sessionId (in sessionStorage, lazy) ===
  const [sessionId, setSessionId] = useState<string>(() => {
    const stored = sessionStorage.getItem(STORAGE_KEY_SESSION);
    if (stored) return stored;
    const fresh = crypto.randomUUID();
    sessionStorage.setItem(STORAGE_KEY_SESSION, fresh);
    return fresh;
  });

  // === status ===
  const [status, setStatus] = useState<"connecting" | "connected" | "disconnected">("connecting");
  const [exitCode, setExitCode] = useState<number | undefined>();

  // === panel state ===
  const [panelState, setPanelState] = useState<PanelState>(() => loadPanelState());

  // === xterm + WS refs (moved from Terminal.tsx; the mode change
  // between fullpage and floating only rerenders the wrapper, never
  // touches these refs) ===
  const containerRef = useRef<HTMLDivElement>(null);
  const termRef = useRef<Terminal | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const intentionallyClosedRef = useRef(false);

  const handleReady = useCallback(() => setStatus("connected"), []);
  const handleDisconnected = useCallback((code?: number) => {
    setStatus("disconnected");
    setExitCode(code);
  }, []);

  // === xterm + WS lifecycle — runs ONCE per sessionId, regardless of mode ===
  useEffect(() => {
    if (!containerRef.current) return;
    intentionallyClosedRef.current = false;

    const term = new Terminal({
      cursorBlink: true,
      cursorStyle: "block",
      fontSize: 14,
      fontFamily: "'JetBrains Mono', 'Fira Code', 'Courier New', monospace",
      theme: {
        background: "#0a0a0a",
        foreground: "#e0e0e0",
        cursor: "#10B981",
        selectionBackground: "rgba(16, 185, 129, 0.3)",
        black: "#000000",
        red: "#ff5555",
        green: "#50fa7b",
        yellow: "#f1fa8c",
        blue: "#bd93f9",
        magenta: "#ff79c6",
        cyan: "#8be9fd",
        white: "#f8f8f2",
        brightBlack: "#6272a4",
        brightRed: "#ff6e6e",
        brightGreen: "#69ff94",
        brightYellow: "#ffffa5",
        brightBlue: "#d6acff",
        brightMagenta: "#ff92df",
        brightCyan: "#a4ffff",
        brightWhite: "#ffffff",
      },
      allowTransparency: true,
      convertEol: true,
    });
    const fitAddon = new FitAddon();
    term.loadAddon(fitAddon);
    term.open(containerRef.current);
    setTimeout(() => fitAddon.fit(), 50);
    termRef.current = term;

    const openSocket = () => {
      const ws = new WebSocket(`${WS_BASE}?session=${sessionId}`);
      wsRef.current = ws;

      ws.onopen = () => {
        reconnectAttemptsRef.current = 0;
        term.focus();
        const dims = fitAddon.proposeDimensions();
        if (dims) {
          ws.send(JSON.stringify({ type: "resize", cols: dims.cols, rows: dims.rows }));
        }
      };

      ws.onmessage = (event) => {
        if (typeof event.data === "string" && event.data.startsWith("{")) {
          try {
            const msg = JSON.parse(event.data);
            if (msg.type === "ready") {
              handleReady();
              return;
            }
            if (msg.type === "info") {
              term.write(`\r\n${msg.message}\r\n`);
              return;
            }
            if (msg.type === "error") {
              term.write(`\r\n\x1b[31mError: ${msg.message}\x1b[0m\r\n`);
              return;
            }
          } catch {
            // not JSON — fall through to write as bytes
          }
        }
        if (event.data instanceof Blob) {
          event.data.arrayBuffer().then((buf) => {
            term.write(new TextDecoder("utf-8").decode(buf));
          });
        } else {
          term.write(event.data);
        }
      };

      ws.onclose = (event) => {
        if (intentionallyClosedRef.current) return;
        if (event.code === 1000 || event.code === 1001) {
          handleDisconnected(event.code);
          return;
        }
        if (reconnectAttemptsRef.current < MAX_AUTO_RECONNECTS) {
          const attempt = reconnectAttemptsRef.current++;
          const delay = Math.min(
            RECONNECT_BASE_DELAY_MS * 2 ** attempt,
            RECONNECT_MAX_DELAY_MS
          );
          term.write(
            `\r\n\x1b[33mConnection lost — reconnecting in ${Math.round(delay / 100) / 10}s…\x1b[0m\r\n`
          );
          reconnectTimerRef.current = setTimeout(() => {
            if (!intentionallyClosedRef.current) openSocket();
          }, delay);
          return;
        }
        handleDisconnected(event.code);
      };

      term.onData((data) => {
        if (ws.readyState === WebSocket.OPEN) ws.send(data);
      });
    };

    const observer = new ResizeObserver(() => {
      fitAddon.fit();
      const dims = fitAddon.proposeDimensions();
      if (dims && wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.send(
          JSON.stringify({ type: "resize", cols: dims.cols, rows: dims.rows })
        );
      }
    });
    if (containerRef.current) observer.observe(containerRef.current);

    openSocket();

    return () => {
      intentionallyClosedRef.current = true;
      observer.disconnect();
      if (reconnectTimerRef.current !== null) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      term.dispose();
    };
  }, [sessionId, handleReady, handleDisconnected]);

  // === handlers ===
  const handleNewSession = useCallback(() => {
    const fresh = crypto.randomUUID();
    sessionStorage.setItem(STORAGE_KEY_SESSION, fresh);
    setSessionId(fresh);
    setStatus("connecting");
    setExitCode(undefined);
  }, []);

  const handleMaximize = useCallback(() => {
    navigate("/terminal");
  }, [navigate]);

  // === status bits shared by both modes ===
  const statusLabel =
    status === "connected"
      ? "Connected"
      : status === "connecting"
      ? "Connecting…"
      : "Disconnected";
  const statusColor =
    status === "connected" ? "#10B981" : status === "connecting" ? "#F59E0B" : "#EF4444";

  // === Render the xterm mount EXACTLY ONCE at the top level of this
  // component's JSX. React mounts it once; route changes only flip the
  // chrome wrapper above it. The xterm <div> stays in the DOM with the
  // same ref across the fullpage <-> floating morph, so xterm.js keeps
  // writing to a live, attached DOM node.
  //
  // The mount is positioned via CSS to fill whichever region the chrome
  // currently claims (full viewport when mode==="fullpage", panel
  // rect when mode==="floating"). The chrome is rendered on top with
  // pointer-events:none on its background so clicks fall through to xterm.
  const xtermRegionStyle: React.CSSProperties =
    mode === "fullpage"
      ? {
          position: "fixed",
          left: 0,
          top: 56, // below the full-page toolbar
          right: 0,
          bottom: 0,
          padding: 8,
          boxSizing: "border-box",
          zIndex: 498,
        }
      : {
          position: "fixed",
          left: panelState.minimized ? panelState.x : panelState.x + 10,
          top: panelState.minimized ? panelState.y : panelState.y + 36, // below title bar
          width: panelState.minimized ? 0 : panelState.width - 20,
          height: panelState.minimized ? 0 : panelState.height - 50, // minus title + resize handle margin
          zIndex: 998,
        };

  // Hide the xterm mount entirely if the session ended — the chrome's
  // disconnected view will fill the space instead.
  const showXterm = status !== "disconnected";

  return (
    <>
      {/* Xterm mount — anchored, persistent. */}
      {showXterm && (
        <div
          ref={containerRef}
          key={`xterm-${sessionId}`}
          style={{
            ...xtermRegionStyle,
            overflow: "hidden",
            borderRadius: 8,
          }}
        />
      )}

      {/* Chrome on top — pointer-events:none on transparent bg, auto on
          interactive controls (buttons, etc. set pointer-events:auto
          themselves). */}
      {mode === "fullpage" ? (
        <FullPageTerminal
          statusLabel={statusLabel}
          statusColor={statusColor}
          isDarkMode={isDarkMode}
          onNewSession={handleNewSession}
          exitCode={exitCode}
          status={status}
        />
      ) : (
        <FloatingPanel
          panelState={panelState}
          onPanelStateChange={setPanelState}
          onMaximize={handleMaximize}
          onNewSession={handleNewSession}
          title="AI Terminal"
          statusLabel={statusLabel}
          statusColor={statusColor}
          isDarkMode={isDarkMode}
        >
          {/* Empty — xterm is rendered above. The panel is a chrome-only
              container now; the children slot is reserved for future use. */}
          <></>
        </FloatingPanel>
      )}
    </>
  );
}

function FullPageTerminal(props: {
  statusLabel: string;
  statusColor: string;
  isDarkMode: boolean;
  onNewSession: () => void;
  exitCode?: number;
  status: "connecting" | "connected" | "disconnected";
}) {
  const { statusLabel, statusColor, isDarkMode, onNewSession, exitCode, status } = props;
  const colors = {
    bg: isDarkMode ? "rgba(5,5,5,0.0)" : "rgba(245,245,247,0.0)", // transparent over xterm
    surface: isDarkMode ? "rgba(10,10,10,0.85)" : "rgba(255,255,255,0.85)",
    text: isDarkMode ? "#ffffff" : "#1d1d1f",
    muted: isDarkMode ? "rgba(255,255,255,0.55)" : "#6e6e73",
    border: isDarkMode ? "rgba(255,255,255,0.08)" : "#d2d2d7",
  };

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        pointerEvents: "none", // let clicks fall through to xterm
        zIndex: 500,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "8px 16px",
          borderBottom: `1px solid ${colors.border}`,
          backgroundColor: colors.surface,
          height: 48,
          flexShrink: 0,
          pointerEvents: "auto", // toolbar itself is interactive
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
          onClick={onNewSession}
          style={{
            padding: "6px 14px",
            borderRadius: 6,
            border: `1px solid ${colors.border}`,
            background: "transparent",
            color: colors.text,
            fontSize: 13,
            fontWeight: 500,
            cursor: "pointer",
          }}
        >
          New Session
        </button>
      </div>

      {status === "disconnected" && (
        <div
          style={{
            position: "absolute",
            inset: 48,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            gap: 12,
            color: colors.muted,
            backgroundColor: colors.bg,
            pointerEvents: "auto",
          }}
        >
          <span style={{ fontSize: 16 }}>
            Session ended{exitCode != null ? ` (exit code ${exitCode})` : ""}
          </span>
          <button
            onClick={onNewSession}
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
      )}
    </div>
  );
}
