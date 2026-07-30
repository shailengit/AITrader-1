import { useEffect, useRef } from "react";
import { Terminal } from "xterm";
import { FitAddon } from "xterm-addon-fit";
import "xterm/css/xterm.css";

interface TerminalComponentProps {
  sessionId: string;
  onReady?: () => void;
  onDisconnected?: (exitCode?: number) => void;
}

const WS_BASE = (() => {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/api/terminal/ws`;
})();

export function TerminalComponent({ sessionId, onReady, onDisconnected }: TerminalComponentProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const termRef = useRef<Terminal | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const onReadyRef = useRef(onReady);
  const onDisconnectedRef = useRef(onDisconnected);

  // Keep callback refs in sync without triggering re-renders
  onReadyRef.current = onReady;
  onDisconnectedRef.current = onDisconnected;

  useEffect(() => {
    if (!containerRef.current) return;

    // Create xterm.js terminal
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

    // Fit terminal to container after layout settles
    const fitTerminal = () => fitAddon.fit();
    setTimeout(fitTerminal, 50);

    termRef.current = term;

    // Connect WebSocket
    const ws = new WebSocket(`${WS_BASE}?session=${sessionId}`);
    wsRef.current = ws;

    ws.onopen = () => {
      term.focus();
      const dims = fitAddon.proposeDimensions();
      if (dims) {
        ws.send(JSON.stringify({ type: "resize", cols: dims.cols, rows: dims.rows }));
      }
    };

    ws.onmessage = (event) => {
      // Handle JSON control messages from the backend
      if (typeof event.data === "string" && event.data.startsWith("{")) {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === "ready") {
            onReadyRef.current?.();
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
          // Not JSON, treat as regular terminal output
        }
      }

      if (event.data instanceof Blob) {
        event.data.arrayBuffer().then((buf) => {
          const decoder = new TextDecoder("utf-8");
          term.write(decoder.decode(buf));
        });
      } else {
        term.write(event.data);
      }
    };

    ws.onclose = (event) => {
      onDisconnectedRef.current?.(event.code);
    };

    ws.onerror = () => {
      // onclose will fire after this
    };

    // Forward keystrokes to WebSocket
    term.onData((data) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(data);
      }
    });

    // Forward resize events
    const observer = new ResizeObserver(() => {
      fitAddon.fit();
      const dims = fitAddon.proposeDimensions();
      if (dims && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "resize", cols: dims.cols, rows: dims.rows }));
      }
    });
    if (containerRef.current) {
      observer.observe(containerRef.current);
    }

    // Cleanup on unmount or sessionId change
    return () => {
      observer.disconnect();
      ws.close();
      term.dispose();
    };
  }, [sessionId]); // Only reconnect when sessionId changes

  return (
    <div
      ref={containerRef}
      style={{
        width: "100%",
        height: "100%",
        overflow: "hidden",
        borderRadius: 8,
      }}
    />
  );
}
