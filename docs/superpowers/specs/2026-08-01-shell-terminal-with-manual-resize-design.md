# Shell Terminal with Manual Resize

**Date:** 2026-08-01
**Status:** Approved design

## Problem

The web terminal currently auto-launches Claude Code in every new session. The user wants a regular shell (zsh) instead, so they can choose when to run `claude`, `herdr`, or any other CLI tool. Additionally, the user wants to manually control the terminal's column × row dimensions rather than relying solely on the container auto-fit.

## Design

### 1. Backend: Spawn zsh instead of claude

**File:** `backend/app/services/terminal_manager.py`

Change `TerminalSession._spawn()` to run `zsh` instead of `claude`:

```python
# Before:
cmd = ["claude"]
if self.resume:
    cmd.extend(["--resume", self.session_id])

# After:
cmd = ["zsh", "--login"]
```

- The `resume` parameter on `create_session()` is kept for API compatibility but has no effect on shell sessions (shells have no conversation context to restore).
- The session ID is still used for reconnection and scrollback replay — unchanged.
- The `--login` flag ensures zsh loads the user's `.zshrc` / `.zprofile` so `PATH`, aliases, and tools like `herdr` and `claude` are available.

**File:** `backend/app/routers/terminal.py`

Update the info message sent to the client on new session creation:

```python
# Before:
await websocket.send_json({"type": "info", "message": "Starting Claude Code session..."})

# After:
await websocket.send_json({"type": "info", "message": "Starting shell session..."})
```

### 2. Frontend: Clickable dimension badge in toolbar

**File:** `frontend/src/components/terminal/TerminalHost.tsx`

Add a small badge in the full-page terminal toolbar showing the current terminal dimensions (e.g., `120×40`). Clicking it reveals two inline number inputs for cols and rows. Pressing Enter or blurring applies the new size.

**Behavior:**
- **Display state:** Shows `{cols}×{rows}` as a muted badge
- **Edit state:** Clicking the badge replaces it with two `<input type="number">` fields side by side, separated by an `×`
- **Apply:** Pressing Enter or blurring the input sends a `{"type": "resize", "cols": N, "rows": N}` JSON message over the WebSocket (the backend `terminal.py` router already handles this message)
- **Cancel:** Pressing Escape reverts to the display state without applying
- **Auto-resize coexistence:** The ResizeObserver remains active. If the user manually sets dimensions, those are sent to the PTY. If the container later changes size (e.g., window resize), the observer fires again and overrides with the new container-fit dimensions. This is acceptable — the manual resize is a temporary override, not a lock.

**Layout:**
```
┌─ Toolbar ───────────────────────────────────────────────┐
│  AI Terminal  ● Connected     [120×40]  [New Session]  │
└─────────────────────────────────────────────────────────┘
```

The badge sits to the left of the "New Session" button, separated by a small gap.

**State variables (added to `TerminalHost`):**
- `dims: { cols: number, rows: number }` — current terminal dimensions, initialized from the fitAddon proposal on connect
- `editingDims: boolean` — whether the badge is in edit mode
- `editCols: string, editRows: string` — temporary values during editing

### 3. What stays the same

- Floating panel mode — unchanged, still resizable via drag handles
- Scrollback buffer — unchanged, still replays on reconnect
- WebSocket protocol — unchanged, resize messages already handled
- Session lifecycle (grace period, idle cleanup) — unchanged
- The `TerminalComponent` in `Terminal.tsx` — unchanged (it's the older version; `TerminalHost.tsx` is the active one)

## Files Modified

| File | Change |
|------|--------|
| `backend/app/services/terminal_manager.py` | Spawn `zsh --login` instead of `claude` |
| `backend/app/routers/terminal.py` | Update "Starting..." info message |
| `frontend/src/components/terminal/TerminalHost.tsx` | Add dimension badge with inline editing |

## Open Questions (resolved)

- **Q:** Should the resume flag be removed? **A:** No — kept for API compatibility, ignored for shell.
- **Q:** Should manual resize lock the dimensions? **A:** No — the ResizeObserver still fires on container changes and overrides.
- **Q:** What shell? **A:** zsh with `--login` to load user profile.
