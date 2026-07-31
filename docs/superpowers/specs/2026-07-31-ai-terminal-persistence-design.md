# AI Terminal — Persistent Session Across Navigation

**Date:** 2026-07-31
**Status:** Draft
**Author:** Shailendra Kaushik

## Overview

The AI Terminal (`/terminal`) currently mounts inside the `<Layout />` route shell, so navigating to another page unmounts the terminal component, closes the WebSocket, and tears down the user's Claude session — losing both the visible scrollback and Claude's in-memory context.

This spec makes the terminal persistent: a single `TerminalHost` lives at the Layout level and morphs between a full-page view (when the route is `/terminal`) and a floating, draggable, resizable, minimizable panel (when the user navigates anywhere else). The xterm.js instance and the WebSocket are never torn down across navigations, and the backend replays the PTY scrollback on every (re)connect so the visible history is restored verbatim.

Claude's own conversation state is preserved via two layers: (1) the PTY child is kept alive across navigations within the 1-hour grace window, and (2) on the rare kill-and-respawn path (idle timeout, crash), Claude is spawned with `--resume <sessionId>` so its conversation context survives.

### Goals

- Navigating away from `/terminal` never destroys the Claude session or the visible scrollback.
- Navigating back to `/terminal` snaps the floating panel back into the full-page view with full state.
- The existing connection, idle, and "New Session" behaviors are preserved.

### Non-Goals

- Multiple parallel Claude sessions (single-session invariant).
- Persistent sessions across tab close (current 1-hour grace is unchanged).
- A portal that survives exiting to the landing page (terminal stays inside `<Layout />`).
- Customizing panel theme, color, or shortcuts beyond what's listed here.

## Architecture

```
Browser
┌────────────────────────────────────────────────────────────┐
│ <Layout>                                                   │
│   <Outlet />         ← currently renders the child route   │
│   <TerminalHost />   ← NEW: always mounted at Layout level │
│      ├─ if route == /terminal → full-page terminal         │
│      └─ else              → floating panel (draggable)     │
└────────────────────────────────────────────────────────────┘

Backend (changes to existing)
┌────────────────────────────────────────────────────────────┐
│ TerminalSession                                            │
│   + scrollback_log: deque[bytes]   (capped at 256 KB)      │
│   + seq: int                       (monotonic)             │
│   on read → append to scrollback_log, bump seq             │
│                                                            │
│ WS /api/terminal/ws                                         │
│   on connect → 1) send {ready}                             │
│                2) replay scrollback_log                    │
│                3) resume live stream                       │
└────────────────────────────────────────────────────────────┘
```

The xterm.js instance and the WebSocket connection live exactly once, mounted at the Layout level. Navigation from `/terminal` to `/sectors` doesn't unmount them — it just changes the wrapping container.

## Components

### Frontend

#### 1. `frontend/src/components/terminal/TerminalHost.tsx` (NEW)

Owns the xterm instance, the WebSocket connection, the auto-reconnect logic, and the sessionId lifecycle. Wraps `TerminalComponent` (or contains its current logic inline).

**Props:** none — `TerminalHost` is self-contained at the Layout level.

**State:**
- `mode: "fullpage" | "floating"` — derived from `useLocation().pathname === "/terminal"`. No internal state needed; the route is the source of truth.
- `panelState: { x, y, width, height, minimized }` — persisted in `localStorage` under `terminal_panel_state`. Default: `{ x: window.innerWidth - 620, y: window.innerHeight - 420, width: 600, height: 400, minimized: false }`.
- `sessionId: string` — moved up from `pages/Terminal.tsx`. Persisted in `sessionStorage`. Lazily generated via `crypto.randomUUID()` on first mount.

**Behavior:**
- Renders one of two children based on `mode`:
  - `mode === "fullpage"`: returns a full-viewport container with the toolbar and the xterm mount
  - `mode === "floating"`: returns `<FloatingPanel>{...}</FloatingPanel>` with the same xterm mount
- The xterm mount is the same DOM node in both modes — only the wrapping container changes (the xterm instance survives the morph)
- All existing `TerminalComponent` logic (xterm init, WS connection, auto-reconnect with backoff, `intentionallyClosedRef`, resize observer) moves here essentially unchanged
- Toolbar status indicator ("Connected" / "Connecting..." / "Disconnected") is shown in both modes; in floating mode it lives in the panel header

**Why this preserves the session:**
- `<TerminalHost />` is a sibling of `<Outlet />` inside `<Layout />`, NOT inside `<Outlet />`. Route changes inside `<Layout />` only re-render the `<Outlet />`'s child; siblings persist. The xterm instance and WS are siblings of the outlet, so they are not affected.
- The `mode` swap is a pure React rerender with the same xterm ref attached — no `useEffect` cleanup triggers, no WebSocket teardown.

#### 2. `frontend/src/components/terminal/FloatingPanel.tsx` (NEW)

A draggable, resizable, minimizable, maximizable container.

**Props:**
```ts
{
  panelState: { x, y, width, height, minimized: boolean };
  onPanelStateChange: (next: PanelState) => void;
  onMaximize?: () => void;     // route change to /terminal
  onNewSession?: () => void;
  title: string;
  statusLabel: string;
  statusColor: string;
  isDarkMode: boolean;
  children: ReactNode;
}
```

**Behavior:**
- Drag: title bar is the drag handle; pointermove updates `x`/`y`; constrained to viewport bounds (`x ≥ 0`, `y ≥ 0`, `x + width ≤ window.innerWidth`, `y + height ≤ window.innerHeight`).
- Resize: corner handle (bottom-right) is the resize handle; pointermove updates `width`/`height`; min 320×200, max 90% of viewport.
- Minimize: collapses to a 200×40 chip anchored to the panel's last `x`/`y` (top-right corner of panel). Chip shows "AI Terminal — {statusLabel}". Click restores.
- Maximize: navigates to `/terminal` via `useNavigate()` (which flips `mode` back to "fullpage" in `TerminalHost`).
- Close / "End session": calls `onNewSession` after a confirm dialog ("End current Claude session?"). Same as the existing "New Session" button.
- Persists `panelState` to `localStorage` on every change. React state updates immediately on pointermove; the localStorage write is debounced to 250 ms to avoid hammering disk during a drag.

**Keyboard:**
- Esc while the panel has focus → minimize the panel
- Cmd/Ctrl+. while anywhere in the app → toggle minimize
- Both bindings are no-ops when the user is currently typing into an `<input>` / `<textarea>` / xterm (don't steal keystrokes from the terminal itself)

#### 3. `frontend/src/components/layout/Layout.tsx` (MODIFY)

Add `<TerminalHost />` as a sibling of `<Outlet />`:

```tsx
return (
  <div className="layout">
    <Sidebar />
    <main>
      <Outlet />
    </main>
    <TerminalHost />   {/* NEW: always mounted */}
  </div>
);
```

Critical: do NOT put `<TerminalHost />` inside `<Outlet />`. It must be a sibling so route changes don't unmount it.

#### 4. `frontend/src/pages/Terminal.tsx` (MODIFY — minimal)

Becomes a no-op stub:

```tsx
export default function TerminalPage() {
  return null;
}
```

Rationale: the route still needs a component to satisfy `App.tsx`'s `<Route element={<TerminalPage />} />`, but all terminal behavior (xterm, WS, sessionId, full-page chrome, floating panel) is now owned by `TerminalHost` at the Layout level. `TerminalHost` reads `useLocation().pathname` to decide whether to render in full-page or floating mode. The page component exists only as a route placeholder.

#### 5. `frontend/src/App.tsx` (UNCHANGED)

Routes remain as-is. The `/terminal` route's component is the no-op stub from §4.

### Backend

#### 6. `backend/app/services/terminal_manager.py` (MODIFY)

**`TerminalSession` additions:**

```python
class TerminalSession:
    SCROLLBACK_MAX_BYTES = 256 * 1024  # 256 KB cap

    def __init__(self, session_id: str):
        # ... existing fields ...
        self._scrollback: deque[bytes] = deque()
        self._scrollback_bytes = 0
        self._scrollback_seq = 0
        self._scrollback_lock = threading.Lock()
```

**New methods:**

```python
def append_scrollback(self, chunk: bytes) -> None:
    """Append PTY output to the scrollback ring buffer. Trims oldest
    bytes when over the cap. Called from the on_pty_readable path."""
    with self._scrollback_lock:
        self._scrollback.append(chunk)
        self._scrollback_bytes += len(chunk)
        self._scrollback_seq += 1
        while self._scrollback_bytes > self.SCROLLBACK_MAX_BYTES and self._scrollback:
            old = self._scrollback.popleft()
            self._scrollback_bytes -= len(old)

def get_scrollback(self) -> tuple[bytes, int]:
    """Returns (concat_scrollback, current_seq)."""
    with self._scrollback_lock:
        return b"".join(self._scrollback), self._scrollback_seq
```

**`TerminalSession._spawn` modification — add `--resume` on respawn:**

The current spawn is `ptyprocess.PtyProcess.spawn(["claude"], cwd=PROJECT_ROOT)`. Add a flag so the router can request a respawn that includes the resume flag:

```python
def _spawn(self, resume: bool = False):
    try:
        cmd = ["claude"]
        if resume:
            # Claude CLI accepts --resume <sessionId> or --continue.
            # Using --resume with our sessionId works when the user
            # has previously used /rename or has Claude's session
            # persistence enabled.
            cmd.extend(["--resume", self.session_id])
        proc = ptyprocess.PtyProcess.spawn(cmd, cwd=PROJECT_ROOT)
        # ... rest unchanged ...
```

`TerminalSession.__init__` keeps the default `resume=False` (initial spawn).

**`TerminalManager.create_session` modification — signal resume flag:**

```python
def create_session(self, session_id: str, *, resume: bool = False) -> TerminalSession:
    """Reuse a live session if one exists (cancelling any pending
    destroy), otherwise create a new one.

    If ``resume=True`` and no live session exists, the new session is
    spawned with ``claude --resume <sessionId>`` so its conversation
    context is restored from Claude's own session store.
    """
    # ... existing logic ...
    if existing is not None:
        return existing
    session = TerminalSession(session_id, resume=resume)  # pass through
    # ... existing logic ...
```

Add `resume: bool = False` to `TerminalSession.__init__`.

#### 7. `backend/app/routers/terminal.py` (MODIFY)

**Replay scrollback after `{type: "ready"}`:**

```python
# In terminal_ws, after sending {ready} (both initial and reconnect paths):
scrollback, _ = term_session.get_scrollback()
if scrollback:
    await websocket.send_bytes(scrollback)
```

**Append to scrollback on every PTY read:**

```python
def on_pty_readable() -> None:
    nonlocal exit_sent
    try:
        data = term_session.read_nonblocking()
    except Exception as e:
        logger.warning("PTY read error: %s", e)
        return
    if data:
        term_session.append_scrollback(data)   # NEW
        asyncio.ensure_future(_safe_send_bytes(data), loop=loop)
        return
    # ... rest unchanged ...
```

**Pass `resume=True` when recreating a session whose Claude child died:**

```python
# At line 71 of terminal.py: term_session = manager.create_session(session)
term_session = manager.create_session(session, resume=True)
```

This is the kill-and-respawn path (e.g. user explicitly exited Claude); preserving conversation context matters most here.

#### 8. Backend module singleton (UNCHANGED)

`manager = TerminalManager()` stays. `destroy_grace_seconds = 3600.0` (1 hour) stays.

## Data Flow

### Successful navigation away → back (within seconds)

```
User on /terminal, types "ls"
  → xterm fires onData
  → TerminalHost WS sends bytes
  → router/terminal.py forwards to PTY
  → PTY child writes output
  → on_pty_readable: read_nonblocking → append_scrollback → send_bytes
  → xterm renders output

User clicks "Sectors" in nav
  → React Router swaps <Outlet /> child (TerminalPage stub → SectorRotation)
  → TerminalHost sibling stays mounted; mode flips to "floating"
  → xterm DOM and WS untouched; layout wrapper animates to bottom-right panel

User clicks "Terminal" in nav
  → mode flips back to "fullpage"
  → Panel animates out; full-page terminal chrome reappears
  → xterm DOM and WS untouched; user sees their previous scrollback
```

### Reconnect (e.g. network blip while floating)

```
WS closes unexpectedly
  → TerminalHost's reconnect logic: setTimeout(openSocket, backoff)
  → New WS opens
  → Backend: get_session(sessionId) → live session; cancel_pending_destroy
  → Backend sends {type: "ready", reconnected: true}
  → Backend reads scrollback_log → sends bytes
  → Frontend WS message handler: write bytes to xterm
  → xterm rebuilds visible history
  → Backend resumes live stream via loop.add_reader
```

### Kill-and-respawn (rare, after idle timeout or crash)

```
Backend's grace timer fires
  → manager._finalize_destroy: kill Claude child, remove from _sessions
  → User navigates back to /terminal (or panel is still floating)
  → TerminalHost reconnect: WS opens
  → Backend: get_session returns None → create_session(sessionId, resume=True)
  → Spawn `claude --resume <sessionId>` in fresh PTY
  → Claude restores its conversation from its own session store
  → PTY outputs Claude's restored context
  → on_pty_readable appends to NEW scrollback_log; sends to xterm
  → User sees Claude's previous conversation continuing
```

## Error Handling

| Scenario | Behavior |
|---|---|
| Navigate away → back within seconds | Panel → full-page morph; WS stays open; no reconnect |
| Navigate away → back after 30 min idle | Backend grace (1h) hasn't expired; session reclaimed; scrollback replayed |
| Navigate away → back after 2 hours idle | Grace expired; Claude child killed; respawned with `--resume`; user sees "Previous session ended. Starting new Claude Code session…" (existing reconnect path handles this) |
| Network blip while floating | Existing auto-reconnect kicks in, scrollback replayed, no visual loss |
| User clicks "New Session" while detached | Confirm dialog ("End current session?") then destroy old + spawn new; panel shows blank → "ready" → empty scrollback |
| User closes tab while session running | WS closes; backend schedules destroy in 1h; user can return within that window from same browser (existing behavior) |
| User opens second tab | Each tab gets its own WS but reuses the same `sessionId` from `sessionStorage`; backend PTY is shared — second tab sees the same live output as first (existing behavior, unchanged) |
| Claude crashes during navigation | Backend marks session dead; on reconnect `terminal.py` respawns with `resume=True`; Claude restores via `--resume` |
| User navigates very fast (spam-click) | Each navigation is idempotent — TerminalHost doesn't remount; only the wrapper container updates |
| StrictMode double-mount (dev) | TerminalHost's existing logic (already hardened against this — `intentionallyClosedRef`) keeps working since the component is mounted once at the Layout level |
| Scrollback cap exceeded | Oldest bytes drop off the ring buffer; user sees truncated scrollback on reattach (acceptable — equivalent to scrolling past top of a real terminal) |
| Panel dragged off-screen (e.g. external display disconnected) | On next pointer event, snap panel back into viewport bounds |
| Browser zoom changes | Panel recomputes its bounds on `resize` event |

## Files Summary

| File | Action |
|---|---|
| `frontend/src/components/terminal/TerminalHost.tsx` | **Create** — Layout-level host owning xterm + WS |
| `frontend/src/components/terminal/FloatingPanel.tsx` | **Create** — draggable/resizable/minimizable/maximizable container |
| `frontend/src/components/layout/Layout.tsx` | **Modify** — render `<TerminalHost />` as sibling of `<Outlet />` |
| `frontend/src/pages/Terminal.tsx` | **Modify** — collapse to no-op stub (route stays valid) |
| `backend/app/services/terminal_manager.py` | **Modify** — add scrollback ring buffer; add `--resume` flag |
| `backend/app/routers/terminal.py` | **Modify** — append to scrollback on read; replay on connect; pass `resume=True` on respawn |

## Testing

### Frontend

- **Playwright e2e — scrollback survives navigation:**
  1. Open `/terminal`
  2. Wait for `Connected`
  3. Type `ls` + Enter; verify output appears
  4. Navigate to `/sectors`
  5. Verify floating panel is visible
  6. Verify `ls` output is still in the panel
  7. Navigate back to `/terminal`
  8. Verify full-page view shows `ls` output
- **Playwright — panel mechanics:**
  - Drag panel from one corner to another; verify position persists across reload
  - Resize panel; verify size persists
  - Minimize panel; verify chip shows correct status
  - Restore panel; verify scrollback intact
  - Maximize panel; verify route changes to `/terminal`
- **Playwright — single-mount invariant:**
  - Add `console.log('TerminalHost mount')` and `console.log('TerminalHost unmount')` in a dev build
  - Navigate /terminal → /sectors → /terminal → /screener → /terminal
  - Verify "unmount" never fires
- **Unit — TerminalHost:**
  - Renders without crashing when not at /terminal
  - `mode` flips based on `useLocation`

### Backend

- **Unit — `TerminalSession.append_scrollback`:**
  - Empty buffer accepts bytes
  - Bytes beyond `SCROLLBACK_MAX_BYTES` evict oldest first
  - Concatenated output matches input in order
  - Thread-safe under concurrent appends
- **Unit — `TerminalSession.get_scrollback`:**
  - Returns empty bytes when no output has been written
  - Returns concatenated bytes + monotonic seq
- **Integration — WS connect order:**
  - Spawn a test session that writes known output (`echo hello`)
  - Connect WS
  - Assert message order: `{type: "ready"}` → `b"hello\n..."` → live stream
- **Integration — `--resume` respawn:**
  - Create session A, write some output, force-kill the Claude child
  - Reconnect → assert `claude --resume A` is in the spawn argv

## Open Questions

None. All design questions resolved during brainstorming:
- Session scope: persistent across days (within 1h grace)
- What survives: conversation + scrollback + background work
- UI: floating detachable panel
- Detach trigger: auto-detach on navigation
- Restoration: backend scrollback replay
- Expiry: 1-hour grace (unchanged)
- Multiple sessions: single only
- Panel UX: full-featured (drag/resize/minimize/maximize)
- Routing: Layout-level mount
- Claude resume: yes, `--resume <sessionId>` on respawn
