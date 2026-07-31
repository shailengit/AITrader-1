import { useEffect, useRef, type ReactNode } from "react";

export type PanelState = {
  x: number;
  y: number;
  width: number;
  height: number;
  minimized: boolean;
};

const MIN_WIDTH = 320;
const MIN_HEIGHT = 200;

export function clampPanelState(
  state: PanelState,
  viewport: { width: number; height: number }
): PanelState {
  const width = Math.max(MIN_WIDTH, Math.min(state.width, viewport.width * 0.9));
  const height = Math.max(MIN_HEIGHT, Math.min(state.height, viewport.height * 0.9));
  const x = Math.max(0, Math.min(state.x, viewport.width - width));
  const y = Math.max(0, Math.min(state.y, viewport.height - height));
  return { ...state, x, y, width, height };
}

type FloatingPanelProps = {
  panelState: PanelState;
  onPanelStateChange: (next: PanelState) => void;
  onMaximize?: () => void;
  onNewSession?: () => void;
  title: string;
  statusLabel: string;
  statusColor: string;
  isDarkMode: boolean;
  children: ReactNode;
};

const LOCAL_STORAGE_KEY = "terminal_panel_state";
const DEBOUNCE_MS = 250;

export function FloatingPanel(props: FloatingPanelProps) {
  const {
    panelState,
    onPanelStateChange,
    onMaximize,
    onNewSession,
    title,
    statusLabel,
    statusColor,
    isDarkMode,
    children,
  } = props;

  const dragRef = useRef<{ startX: number; startY: number; x: number; y: number } | null>(null);
  const resizeRef = useRef<{ startX: number; startY: number; w: number; h: number } | null>(null);
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Debounced localStorage persistence — React state updates immediately
  // during a drag/resize; only the disk write is debounced to avoid
  // hammering localStorage on every pointermove.
  useEffect(() => {
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(() => {
      try {
        localStorage.setItem(LOCAL_STORAGE_KEY, JSON.stringify(panelState));
      } catch {
        // localStorage may be unavailable (private mode, etc.) — ignore.
      }
    }, DEBOUNCE_MS);
    return () => {
      if (saveTimerRef.current) {
        clearTimeout(saveTimerRef.current);
        saveTimerRef.current = null;
      }
    };
  }, [panelState]);

  function clamp(next: PanelState): PanelState {
    return clampPanelState(next, {
      width: window.innerWidth,
      height: window.innerHeight,
    });
  }

  function onTitlePointerDown(e: React.PointerEvent<HTMLDivElement>) {
    if (panelState.minimized) return;
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
    dragRef.current = { startX: e.clientX, startY: e.clientY, x: panelState.x, y: panelState.y };
  }
  function onTitlePointerMove(e: React.PointerEvent<HTMLDivElement>) {
    if (!dragRef.current) return;
    const dx = e.clientX - dragRef.current.startX;
    const dy = e.clientY - dragRef.current.startY;
    onPanelStateChange(
      clamp({ ...panelState, x: dragRef.current.x + dx, y: dragRef.current.y + dy })
    );
  }
  function onTitlePointerUp(e: React.PointerEvent<HTMLDivElement>) {
    dragRef.current = null;
    (e.target as HTMLElement).releasePointerCapture(e.pointerId);
  }

  function onResizePointerDown(e: React.PointerEvent<HTMLDivElement>) {
    if (panelState.minimized) return;
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
    resizeRef.current = {
      startX: e.clientX,
      startY: e.clientY,
      w: panelState.width,
      h: panelState.height,
    };
  }
  function onResizePointerMove(e: React.PointerEvent<HTMLDivElement>) {
    if (!resizeRef.current) return;
    const dw = e.clientX - resizeRef.current.startX;
    const dh = e.clientY - resizeRef.current.startY;
    onPanelStateChange(
      clamp({ ...panelState, width: resizeRef.current.w + dw, height: resizeRef.current.h + dh })
    );
  }
  function onResizePointerUp(e: React.PointerEvent<HTMLDivElement>) {
    resizeRef.current = null;
    (e.target as HTMLElement).releasePointerCapture(e.pointerId);
  }

  // Keyboard: Esc minimizes when the panel has focus.
  function onKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    if (e.key === "Escape") {
      e.stopPropagation();
      onPanelStateChange({ ...panelState, minimized: true });
    }
  }

  // Cmd/Ctrl+. toggles minimize globally, but only when the user is not
  // typing in an <input>, <textarea>, or xterm mount — we must not
  // steal keystrokes the terminal itself relies on.
  useEffect(() => {
    function onGlobalKey(e: KeyboardEvent) {
      if (!(e.metaKey || e.ctrlKey) || e.key !== ".") return;
      const target = e.target as HTMLElement | null;
      if (!target) return;
      const tag = target.tagName?.toLowerCase();
      if (tag === "input" || tag === "textarea") return;
      if (target.closest(".xterm")) return;
      e.preventDefault();
      onPanelStateChange({ ...panelState, minimized: !panelState.minimized });
    }
    window.addEventListener("keydown", onGlobalKey);
    return () => window.removeEventListener("keydown", onGlobalKey);
  }, [panelState, onPanelStateChange]);

  const surface = isDarkMode ? "rgba(10,10,10,0.95)" : "rgba(255,255,255,0.95)";
  const border = isDarkMode ? "rgba(255,255,255,0.10)" : "rgba(0,0,0,0.10)";
  const text = isDarkMode ? "#fff" : "#1d1d1f";

  if (panelState.minimized) {
    return (
      <div
        role="dialog"
        aria-label={title}
        style={{
          position: "fixed",
          left: panelState.x,
          top: panelState.y,
          width: 200,
          height: 40,
          backgroundColor: surface,
          border: `1px solid ${border}`,
          borderRadius: 8,
          boxShadow: "0 6px 24px rgba(0,0,0,0.25)",
          display: "flex",
          alignItems: "center",
          gap: 8,
          padding: "0 12px",
          cursor: "pointer",
          color: text,
          zIndex: 1000,
        }}
        onClick={() => onPanelStateChange({ ...panelState, minimized: false })}
      >
        <span
          style={{
            width: 8,
            height: 8,
            borderRadius: "50%",
            backgroundColor: statusColor,
          }}
        />
        <span style={{ fontSize: 12, fontWeight: 600 }}>{title}</span>
        <span style={{ fontSize: 11, opacity: 0.6 }}>— {statusLabel}</span>
      </div>
    );
  }

  return (
    <div
      role="dialog"
      aria-label={title}
      onKeyDown={onKeyDown}
      tabIndex={-1}
      style={{
        position: "fixed",
        left: panelState.x,
        top: panelState.y,
        width: panelState.width,
        height: panelState.height,
        backgroundColor: "transparent", // transparent so xterm (rendered underneath) shows through
        border: `1px solid ${border}`,
        borderRadius: 8,
        boxShadow: "0 12px 32px rgba(0,0,0,0.30)",
        display: "flex",
        flexDirection: "column",
        color: text,
        zIndex: 1000,
        overflow: "hidden",
        pointerEvents: "none", // let clicks fall through to the xterm beneath; interactive children re-enable
      }}
    >
      {/* Title bar — drag handle. pointer-events:auto so the drag
          handle and buttons are interactive despite the parent being
          pointer-events:none. */}
      <div
        role="banner"
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "6px 10px",
          borderBottom: `1px solid ${border}`,
          backgroundColor: surface,
          cursor: "grab",
          userSelect: "none",
          gap: 8,
          height: 36,
          flexShrink: 0,
          pointerEvents: "auto",
        }}
        onPointerDown={onTitlePointerDown}
        onPointerMove={onTitlePointerMove}
        onPointerUp={onTitlePointerUp}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: "50%",
              backgroundColor: statusColor,
            }}
          />
          <span style={{ fontSize: 13, fontWeight: 600 }}>{title}</span>
          <span style={{ fontSize: 11, opacity: 0.6 }}>{statusLabel}</span>
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          {onNewSession && (
            <button
              onClick={() => {
                if (window.confirm("End current Claude session?")) onNewSession();
              }}
              aria-label="End session"
              style={{
                padding: "2px 8px",
                fontSize: 11,
                borderRadius: 4,
                border: `1px solid ${border}`,
                background: "transparent",
                color: text,
                cursor: "pointer",
              }}
            >
              New
            </button>
          )}
          <button
            onClick={() => onPanelStateChange({ ...panelState, minimized: true })}
            aria-label="Minimize"
            style={{
              padding: "2px 8px",
              fontSize: 11,
              borderRadius: 4,
              border: `1px solid ${border}`,
              background: "transparent",
              color: text,
              cursor: "pointer",
            }}
          >
            _
          </button>
          {onMaximize && (
            <button
              onClick={onMaximize}
              aria-label="Maximize"
              style={{
                padding: "2px 8px",
                fontSize: 11,
                borderRadius: 4,
                border: `1px solid ${border}`,
                background: "transparent",
                color: text,
                cursor: "pointer",
              }}
            >
              ▢
            </button>
          )}
        </div>
      </div>

      {/* Body — transparent so the xterm mount rendered at the top
          level of TerminalHost (positioned underneath via z-index) is
          visible through the panel chrome. The title bar has its own
          opaque background. */}
      <div style={{ flex: 1, overflow: "hidden", position: "relative", backgroundColor: "transparent" }}>{children}</div>

      {/* Resize handle */}
      <div
        role="separator"
        aria-label="Resize handle"
        onPointerDown={onResizePointerDown}
        onPointerMove={onResizePointerMove}
        onPointerUp={onResizePointerUp}
        style={{
          position: "absolute",
          right: 0,
          bottom: 0,
          width: 14,
          height: 14,
          cursor: "nwse-resize",
          background: `linear-gradient(135deg, transparent 50%, ${border} 50%)`,
          pointerEvents: "auto",
        }}
      />
    </div>
  );
}
