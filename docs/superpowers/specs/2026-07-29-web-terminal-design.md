# Web Terminal — Claude Code CLI in the Browser

**Date:** 2026-07-29
**Status:** Draft
**Author:** Shailendra Kaushik

## Overview

Embed the full Claude Code CLI experience inside the TradeCraft webapp by wrapping the real `claude` CLI process in a browser-based terminal. The user gets 100% of Claude Code's capabilities (bash, file ops, git, skills, MCP servers) without leaving the browser.

## Architecture

```
Browser (xterm.js)                     FastAPI Backend
┌─────────────────────────┐            ┌──────────────────────────────┐
│  /terminal route         │  WS connect │  /api/terminal/ws           │
│  ┌───────────────────┐   │ ─────────→ │  ┌────────────────────────┐  │
│  │ xterm.js terminal  │   │  stdin/    │  │ PTY (ptyprocess)       │  │
│  │ (full viewport)    │   │  stdout   │  │  ┌──────────────────┐  │  │
│  └───────────────────┘   │ ←──────── │  │  │ claude CLI       │  │  │
│                          │            │  │  │ (headless)       │  │  │
│  Toolbar:                │            │  │  └──────────────────┘  │  │
│  [New Session] Status    │            │  └────────────────────────┘  │
│  "Connected"             │            │                              │
└─────────────────────────┘            │  Session Manager:            │
                                       │  - 1 process per WS conn    │
                                       │  - Auto-kill on disconnect   │
                                       │  - Timeout: 30 min idle     │
                                       │  - CWD: project root        │
                                       └──────────────────────────────┘
```

## Components

### Frontend

#### 1. `frontend/src/components/terminal/Terminal.tsx` (NEW)

A reusable React component wrapping xterm.js.

**Props:**
- `sessionId: string` — unique session identifier
- `onDisconnected?: () => void` — callback when WS closes

**Behavior:**
- On mount: generates a UUID `sessionId` (via `crypto.randomUUID()`), creates an xterm.js Terminal instance with the `fit` addon, opens it in a container div, connects to `ws://host/api/terminal/ws?session={sessionId}`
- On keystroke: writes the character to the WebSocket
- On WebSocket message: writes the data to xterm.js (`term.write(data)`)
- On resize: sends `{type: "resize", cols, rows}` to the backend so the PTY dimensions stay in sync
- On unmount: closes the WebSocket (backend kills the Claude process)
- Copy/paste: uses xterm.js built-in selection support

**Dependencies:**
- `xterm` (npm)
- `xterm-addon-fit` (npm)

#### 2. `frontend/src/pages/Terminal.tsx` (NEW)

The full-page terminal view.

**Layout:**
- Toolbar at the top (48px height):
  - "AI Terminal" title (left)
  - Session status indicator: green dot = connected, red = disconnected, yellow = connecting
  - "New Session" button — closes current WS, opens a new one
- Terminal area below: fills remaining viewport height

**States:**
- **Loading:** Shows "Connecting..." with a spinner while the WebSocket connects
- **Connected:** Full xterm.js terminal, interactive
- **Disconnected:** Shows "Session ended" with exit code and "New Session" button
- **Error:** Shows error message with "Retry" button

#### 3. `frontend/src/App.tsx` (MODIFY)

Add route:
```tsx
<Route path="terminal" element={
  <ErrorBoundary>
    <TerminalPage />
  </ErrorBoundary>
} />
```

#### 4. `frontend/src/pages/Landing.tsx` (MODIFY)

Add a new tool card:
```tsx
{
  id: 'terminal',
  title: 'AI Terminal',
  description: 'Full Claude Code CLI in your browser. Read, write, run code, git, and more.',
  icon: Terminal,
  accent: '#10B981',
  link: '/terminal',
  stat: 'Claude Code',
  detail: 'Direct project access with all tools and skills',
}
```

### Backend

#### 5. `backend/app/services/terminal_manager.py` (NEW)

Manages Claude Code processes via pseudo-terminals.

**Class: `TerminalSession`**
- `__init__(self, session_id: str)` — generates a unique session ID
- `start()` — spawns Claude Code via `ptyprocess`:
  ```python
  import ptyprocess
  self.process = ptyprocess.PtyProcess.spawn(
      ["claude"],
      cwd=PROJECT_ROOT,
  )
  ```
- `write(data: str)` — writes to the PTY's stdin
- `read()` — reads from the PTY's stdout (non-blocking)
- `resize(cols: int, rows: int)` — sends SIGWINCH to the PTY
- `kill()` — terminates the Claude Code process
- `is_alive()` — checks if the process is still running

**Class: `TerminalManager`**
- `create_session() -> str` — creates a new `TerminalSession`, returns session_id
- `get_session(session_id) -> TerminalSession` — retrieves a session
- `destroy_session(session_id)` — kills the process and removes the session
- `cleanup_idle(timeout=1800)` — kills sessions idle for 30 minutes

**Edge cases:**
- Claude Code not installed → `start()` raises `FileNotFoundError`, surfaced as a 503
- Claude Code crashes → `read()` returns empty, session marked as dead
- Multiple rapid "New Session" clicks → old session destroyed before new one starts

#### 6. `backend/app/routers/terminal.py` (NEW)

WebSocket endpoint for terminal sessions.

**Endpoints:**

```
WS /api/terminal/ws?session={session_id}
```
- On connect: looks up or creates a `TerminalSession`, starts a background asyncio task that polls `session.read()` and sends output to the WebSocket
- On message: calls `session.write(data)` — forwards keystrokes to Claude Code
- On close: calls `session.kill()` and `manager.destroy_session()`
- JSON control messages: `{type: "resize", cols: N, rows: N}` → `session.resize(cols, rows)`

```
GET /api/terminal/health
```
- Returns `{available: true}` if `claude --version` succeeds, `{available: false, error: "..."}` otherwise

#### 7. `backend/app/main.py` (MODIFY)

Register the terminal router:
```python
from app.routers.terminal import router as terminal_router
app.include_router(terminal_router, prefix="/api")
```

#### 8. `backend/requirements.txt` (MODIFY)

Add:
```
ptyprocess>=0.7.0
websockets>=10.0
```

## Data Flow

```
User types "claude add a volatility filter" in the terminal
  → xterm.js fires a "data" event with the text
  → Terminal.tsx sends it over the WebSocket
  → terminal.py receives the message
  → terminal_manager.py writes it to the PTY's stdin
  → Claude Code receives it as if typed in a real terminal
  → Claude Code processes, runs tools (bash, grep, read, etc.)
  → Claude Code writes output to stdout
  → terminal_manager.py reads from the PTY's stdout
  → terminal.py sends it over the WebSocket
  → Terminal.tsx receives it and calls term.write(data)
  → xterm.js renders it in the browser
```

## Error Handling

| Scenario | Frontend | Backend |
|----------|----------|---------|
| Claude Code crashes | Shows "Session ended (exit code N)" + "New Session" button | Logs exit code, cleans up session |
| WebSocket disconnects | Shows "Reconnecting..." for 10s, then "Disconnected" | Kills Claude process on WS close |
| Idle for 30 min | Shows "Session timed out" | `cleanup_idle()` kills the process |
| Claude Code not installed | Shows "Claude Code not found. Install with: npm install -g @anthropic-ai/claude-code" | Health endpoint returns 503 |
| User closes tab | (automatic) | WS close event → kill process |
| Network blip | Auto-reconnects within 10s, terminal state preserved | New WS connection reuses same session if within timeout |

## Files Summary

| File | Action |
|------|--------|
| `frontend/src/components/terminal/Terminal.tsx` | **Create** — xterm.js React wrapper |
| `frontend/src/pages/Terminal.tsx` | **Create** — full-page terminal view |
| `frontend/src/App.tsx` | **Modify** — add `/terminal` route |
| `frontend/src/pages/Landing.tsx` | **Modify** — add "AI Terminal" card |
| `backend/app/services/terminal_manager.py` | **Create** — PTY session manager |
| `backend/app/routers/terminal.py` | **Create** — WebSocket endpoint |
| `backend/app/main.py` | **Modify** — register terminal router |
| `backend/requirements.txt` | **Modify** — add `ptyprocess` |
