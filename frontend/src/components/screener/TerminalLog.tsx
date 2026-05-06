import { useEffect, useRef } from "react";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import "@xterm/xterm/css/xterm.css";

export interface LogEntry {
  agent: string;
  message: string;
  type: string;
  color: string;
}

interface TerminalLogProps {
  logs: LogEntry[];
  style?: React.CSSProperties;
}

const COLOR_TO_ANSI: Record<string, string> = {
  blue: "\x1B[34m",
  green: "\x1B[32m",
  amber: "\x1B[33m",
  purple: "\x1B[35m",
  red: "\x1B[31m",
  white: "\x1B[37m",
  gray: "\x1B[90m",
};

const RESET = "\x1B[0m";
const BOLD_ON = "\x1B[1m";
const BOLD_OFF = "\x1B[22m";

function formatLogLine(log: LogEntry): string {
  const colorCode = COLOR_TO_ANSI[log.color] || COLOR_TO_ANSI.gray;
  const agent = log.agent || "System";

  // Convert markdown bold **text** to ANSI bold
  let message = log.message;
  message = message.replace(/\*\*(.+?)\*\*/g, `${BOLD_ON}$1${BOLD_OFF}`);

  // Build colored line: [agent] message
  const line = `${colorCode}[${agent}]${RESET} ${message}`;
  return line;
}

export default function TerminalLog({ logs, style }: TerminalLogProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const terminalRef = useRef<Terminal | null>(null);
  const fitAddonRef = useRef<FitAddon | null>(null);
  const lastLogCountRef = useRef(0);

  useEffect(() => {
    if (!containerRef.current) return;

    const terminal = new Terminal({
      cursorBlink: false,
      cursorStyle: "block",
      fontSize: 13,
      fontFamily: "'JetBrains Mono', 'Fira Code', 'Menlo', 'Courier New', monospace",
      theme: {
        background: "#000000",
        foreground: "#d4d4d4",
        cursor: "#000000",
        selectionBackground: "#264f78",
        black: "#000000",
        red: "#ef4444",
        green: "#34d399",
        yellow: "#fbbf24",
        blue: "#60a5fa",
        magenta: "#a78bfa",
        cyan: "#22d3ee",
        white: "#e5e5e5",
        brightBlack: "#6b7280",
        brightRed: "#f87171",
        brightGreen: "#4ade80",
        brightYellow: "#facc15",
        brightBlue: "#93c5fd",
        brightMagenta: "#c4b5fd",
        brightCyan: "#67e8f9",
        brightWhite: "#ffffff",
      },
      convertEol: true,
      scrollback: 1000,
      disableStdin: true,
      allowTransparency: false,
      rows: 12,
    });

    const fitAddon = new FitAddon();
    terminal.loadAddon(fitAddon);
    terminal.open(containerRef.current);
    fitAddon.fit();

    terminalRef.current = terminal;
    fitAddonRef.current = fitAddon;

    // Hide the cursor since this is a read-only log viewer
    terminal.write("\x1B[?25l");

    const handleResize = () => {
      fitAddon.fit();
    };
    window.addEventListener("resize", handleResize);

    // Observe container size changes
    const resizeObserver = new ResizeObserver(() => {
      fitAddon.fit();
    });
    resizeObserver.observe(containerRef.current);

    return () => {
      window.removeEventListener("resize", handleResize);
      resizeObserver.disconnect();
      terminal.dispose();
      terminalRef.current = null;
      fitAddonRef.current = null;
    };
  }, []);

  // Write new logs as they arrive
  useEffect(() => {
    const terminal = terminalRef.current;
    if (!terminal) return;

    const prevCount = lastLogCountRef.current;
    const newLogs = logs.slice(prevCount);

    if (newLogs.length > 0) {
      for (const log of newLogs) {
        terminal.writeln(formatLogLine(log));
      }
      terminal.scrollToBottom();
      lastLogCountRef.current = logs.length;
    }
  }, [logs]);

  return (
    <div
      ref={containerRef}
      style={{
        ...style,
        backgroundColor: "#000000",
        padding: 0,
      }}
    />
  );
}
