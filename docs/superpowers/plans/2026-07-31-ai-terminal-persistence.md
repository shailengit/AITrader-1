# AI Terminal Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the AI Terminal persist across navigation by lifting its host to the Layout level and adding a scrollback replay buffer + `--resume` on the backend.

**Architecture:** A new `<TerminalHost />` lives as a sibling of `<Outlet />` inside `<Layout />` so React Router route changes never unmount it. The host morphs between a full-page chrome (when route is `/terminal`) and a `<FloatingPanel />` chrome (otherwise), keeping the same xterm.js instance and WebSocket across morphs. The backend adds a 256 KB scrollback ring buffer on `TerminalSession` that is replayed to the client on every (re)connect, and the Claude CLI is respawned with `--resume <sessionId>` so its conversation context survives kill-and-respawn paths.

**Tech Stack:** React 19, react-router-dom v7, xterm.js 5, react-router useLocation, FastAPI WebSockets, ptyprocess, threading, deque (Python).

## Global Constraints

- Single-session invariant: only one Claude child process per browser tab at a time.
- Scrollback cap: 256 KB per `TerminalSession` (oldest bytes evicted first).
- Backend grace period: 3600 s (1 hour) — unchanged from existing code.
- The `<TerminalHost />` must be a sibling of `<Outlet />` in `<Layout />`, NEVER inside `<Outlet />` (this is the whole point — route changes must not unmount it).
- `pages/Terminal.tsx` becomes a `return null` no-op stub; `App.tsx` is unchanged.
- FloatingPanel keyboard shortcuts (Esc, Cmd/Ctrl+.) are no-ops when the active element is `<input>`, `<textarea>`, or the xterm mount.
- Scrollback `localStorage` write debounced 250 ms during drag/resize.
- `--resume <sessionId>` is added on the respawn path only (line 71 of `backend/app/routers/terminal.py`), never on first spawn.
- PTY I/O is non-blocking via `os.set_blocking(proc.fd, False)` + `loop.add_reader()` — already in place, do not change.
- Backend tests use pytest + FastAPI TestClient from `backend/tests/conftest.py`.
- Frontend tests use vitest (already configured, see `frontend/src/lib/subScoreInputs.test.ts` for example).

---

## File Structure

**Created:**
- `frontend/src/components/terminal/TerminalHost.tsx` — Layout-level host owning xterm + WS + mode switching
- `frontend/src/components/terminal/FloatingPanel.tsx` — draggable/resizable/minimizable/maximizable container
- `frontend/src/components/terminal/FloatingPanel.test.tsx` — unit tests for panel state clamping + minimize logic
- `frontend/src/components/terminal/TerminalHost.test.tsx` — unit tests for mode derivation from useLocation
- `backend/tests/services/test_terminal_session_scrollback.py` — unit tests for append/get/eviction
- `backend/tests/services/test_terminal_manager_resume.py` — unit tests for resume flag propagation
- `backend/tests/routers/test_terminal_ws_scrollback.py` — integration test for WS replay order

**Modified:**
- `frontend/src/components/layout/Layout.tsx` — add `<TerminalHost />` sibling
- `frontend/src/pages/Terminal.tsx` — collapse to `return null`
- `backend/app/services/terminal_manager.py` — add scrollback buffer + `resume` flag on spawn + on `create_session`
- `backend/app/routers/terminal.py` — call `append_scrollback` on every read, replay after `{ready}`, pass `resume=True` on respawn

**Unchanged:**
- `frontend/src/App.tsx` (routes stay as-is)
- `backend/app/main.py`

---

## Task 1: Backend scrollback buffer on TerminalSession

**Files:**
- Modify: `backend/app/services/terminal_manager.py:34-77` (add scrollback fields + methods)
- Test: `backend/tests/services/test_terminal_session_scrollback.py` (new)

**Interfaces:**
- Consumes: nothing (this is the lowest layer)
- Produces:
  - `TerminalSession.append_scrollback(chunk: bytes) -> None`
  - `TerminalSession.get_scrollback() -> tuple[bytes, int]`
  - `TerminalSession.SCROLLBACK_MAX_BYTES: int` (class attr, 256 * 1024)

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/services/test_terminal_session_scrollback.py`:

```python
"""Tests for TerminalSession scrollback ring buffer."""

from collections import deque

from app.services.terminal_manager import TerminalSession


def test_scrollback_starts_empty():
    sess = TerminalSession.__new__(TerminalSession)  # bypass __init__ (no real PTY)
    sess._scrollback = deque()
    sess._scrollback_bytes = 0
    sess._scrollback_seq = 0
    sess._scrollback_lock = __import__("threading").Lock()

    data, seq = sess.get_scrollback()
    assert data == b""
    assert seq == 0


def test_append_scrollback_returns_recent_bytes_in_order():
    sess = TerminalSession.__new__(TerminalSession)
    import threading
    sess._scrollback = deque()
    sess._scrollback_bytes = 0
    sess._scrollback_seq = 0
    sess._scrollback_lock = threading.Lock()

    sess.append_scrollback(b"hello ")
    sess.append_scrollback(b"world\n")
    data, seq = sess.get_scrollback()
    assert data == b"hello world\n"
    assert seq == 2


def test_append_scrollback_evicts_oldest_when_over_cap():
    sess = TerminalSession.__new__(TerminalSession)
    import threading
    sess._scrollback = deque()
    sess._scrollback_bytes = 0
    sess._scrollback_seq = 0
    sess._scrollback_lock = threading.Lock()

    # Force a small cap for the test by monkeypatching the class attribute.
    original_cap = TerminalSession.SCROLLBACK_MAX_BYTES
    TerminalSession.SCROLLBACK_MAX_BYTES = 10
    try:
        sess.append_scrollback(b"AAAAA")  # 5 bytes, seq 1
        sess.append_scrollback(b"BBBBB")  # 5 bytes, total 10, seq 2
        sess.append_scrollback(b"CCCCC")  # 5 bytes -> trims 5 oldest -> total still 10, seq 3
        data, seq = sess.get_scrollback()
        # Oldest 5 ("AAAAA") were evicted; remainder = "BBBBBCCCCC"
        assert data == b"BBBBBCCCCC"
        assert seq == 3
    finally:
        TerminalSession.SCROLLBACK_MAX_BYTES = original_cap
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./venv/bin/python -m pytest tests/services/test_terminal_session_scrollback.py -v`
Expected: FAIL with `AttributeError: 'TerminalSession' object has no attribute '_scrollback'` (or similar missing-method error).

- [ ] **Step 3: Implement scrollback in TerminalSession**

In `backend/app/services/terminal_manager.py`:

a) Update imports:

```python
import os
import errno
import logging
import time
import threading
from collections import deque
from typing import Optional
import ptyprocess
```

b) Inside `class TerminalSession:`, add the class attribute and update `__init__`:

```python
class TerminalSession:
    """A single Claude Code process running inside a PTY. ... """

    SCROLLBACK_MAX_BYTES = 256 * 1024  # 256 KB cap

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.process: Optional[ptyprocess.PtyProcess] = None
        self.last_activity = time.time()
        self.created_at = time.time()
        self._error: Optional[str] = None
        self._ready = False
        self.ready_event = threading.Event()
        self._lock = threading.Lock()

        # Scrollback ring buffer for replay on (re)connect.
        self._scrollback: deque[bytes] = deque()
        self._scrollback_bytes = 0
        self._scrollback_seq = 0
        self._scrollback_lock = threading.Lock()

        # Start spawn in background thread
        self._spawn_thread = threading.Thread(target=self._spawn, daemon=True)
        self._spawn_thread.start()
```

c) Add new methods immediately after `is_alive`:

```python
    def append_scrollback(self, chunk: bytes) -> None:
        """Append PTY output to the scrollback ring buffer. Trims oldest
        bytes when over ``SCROLLBACK_MAX_BYTES``. Thread-safe."""
        with self._scrollback_lock:
            self._scrollback.append(chunk)
            self._scrollback_bytes += len(chunk)
            self._scrollback_seq += 1
            while (
                self._scrollback_bytes > self.SCROLLBACK_MAX_BYTES
                and self._scrollback
            ):
                old = self._scrollback.popleft()
                self._scrollback_bytes -= len(old)

    def get_scrollback(self) -> tuple[bytes, int]:
        """Return ``(concat_scrollback, current_seq)``. ``current_seq``
        is monotonic and increments once per ``append_scrollback`` call.
        Useful if a future caller wants to request only the tail; current
        replays use the full concatenated buffer."""
        with self._scrollback_lock:
            return b"".join(self._scrollback), self._scrollback_seq
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ./venv/bin/python -m pytest tests/services/test_terminal_session_scrollback.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/terminal_manager.py backend/tests/services/test_terminal_session_scrollback.py
git commit -m "feat(terminal): add bounded scrollback ring buffer to TerminalSession

- Bounded deque with 256 KB cap (oldest bytes evicted first)
- append_scrollback / get_scrollback thread-safe under _scrollback_lock
- Bypasses __init__ in tests so no real PTY is spawned

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 2: Backend `resume` flag on `_spawn` + `create_session`

**Files:**
- Modify: `backend/app/services/terminal_manager.py:35-77, 213-232` (extend `__init__`, `_spawn`, `create_session`)
- Test: `backend/tests/services/test_terminal_manager_resume.py` (new)

**Interfaces:**
- Consumes: `TerminalSession.__init__(session_id, resume: bool = False)`
- Produces: `TerminalSession` whose spawned argv includes `["--resume", session_id]` iff `resume=True`. `TerminalManager.create_session(session_id, *, resume: bool = False) -> TerminalSession`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/services/test_terminal_manager_resume.py`:

```python
"""Tests that --resume propagates from create_session to ptyprocess.spawn."""

import sys
import threading

# Ensure the backend is importable.
sys.path.insert(0, "backend")

from app.services import terminal_manager


def test_spawn_argv_contains_resume_when_resume_true(monkeypatch):
    """When resume=True, the spawned argv must include --resume <session_id>."""
    captured = {}

    class FakePty:
        @staticmethod
        def spawn(argv, cwd=None):
            captured["argv"] = list(argv)
            captured["cwd"] = cwd

            class P:
                fd = 7
                pid = 1234

                def isalive(self):
                    return True

            return P()

    monkeypatch.setattr(terminal_manager.ptyprocess, "PtyProcess", FakePty)
    monkeypatch.setattr(terminal_manager.os, "set_blocking", lambda *_a, **_kw: None)

    sess = terminal_manager.TerminalSession("sess-A", resume=True)
    sess._spawn_thread.join(timeout=5)

    assert captured["argv"][:3] == ["claude", "--resume", "sess-A"], captured["argv"]


def test_spawn_argv_does_not_contain_resume_when_resume_false(monkeypatch):
    captured = {}

    class FakePty:
        @staticmethod
        def spawn(argv, cwd=None):
            captured["argv"] = list(argv)

            class P:
                fd = 7
                pid = 1234

                def isalive(self):
                    return True

            return P()

    monkeypatch.setattr(terminal_manager.ptyprocess, "PtyProcess", FakePty)
    monkeypatch.setattr(terminal_manager.os, "set_blocking", lambda *_a, **_kw: None)

    sess = terminal_manager.TerminalSession("sess-B", resume=False)
    sess._spawn_thread.join(timeout=5)

    assert captured["argv"] == ["claude"], captured["argv"]


def test_create_session_passes_resume_through(monkeypatch):
    from app.services.terminal_manager import TerminalManager

    mgr = TerminalManager()

    captured_kwargs = {}

    class FakeTerminalSession:
        def __init__(self, session_id, resume=False):
            captured_kwargs["session_id"] = session_id
            captured_kwargs["resume"] = resume
            self.session_id = session_id
            self.is_alive = lambda: True

    monkeypatch.setattr(terminal_manager, "TerminalSession", FakeTerminalSession)

    # Pre-populate _sessions to force the "create new" branch (not the reclaim branch).
    mgr._sessions["sess-C"] = "placeholder"  # any sentinel; we want create_session to skip the live branch

    result = mgr.create_session("sess-C", resume=True)
    assert captured_kwargs == {"session_id": "sess-C", "resume": True}
```

Note: the third test depends on `create_session` not reusing an existing live session when one is present. We pre-populate `_sessions` with a sentinel object — `create_session` must skip the live-reuse path when called with a new session id. Re-read the current `create_session` logic in step 3 if needed.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./venv/bin/python -m pytest tests/services/test_terminal_manager_resume.py -v`
Expected: FAIL — `TerminalSession.__init__` does not accept `resume`, or `_spawn` does not pass it through.

- [ ] **Step 3: Implement resume propagation**

a) Update `TerminalSession.__init__`:

```python
    def __init__(self, session_id: str, resume: bool = False):
        self.session_id = session_id
        self.resume = resume
        self.process: Optional[ptyprocess.PtyProcess] = None
        self.last_activity = time.time()
        self.created_at = time.time()
        self._error: Optional[str] = None
        self._ready = False
        self.ready_event = threading.Event()
        self._lock = threading.Lock()

        self._scrollback: deque[bytes] = deque()
        self._scrollback_bytes = 0
        self._scrollback_seq = 0
        self._scrollback_lock = threading.Lock()

        self._spawn_thread = threading.Thread(target=self._spawn, daemon=True)
        self._spawn_thread.start()
```

b) Update `_spawn`:

```python
    def _spawn(self):
        """Spawn Claude Code inside a pseudo-terminal (runs in background thread)."""
        try:
            cmd = ["claude"]
            if self.resume:
                # Claude CLI accepts --resume <sessionId> to restore its
                # conversation from its own session store. The flag is
                # only set on the respawn path; initial spawn uses a
                # fresh session.
                cmd.extend(["--resume", self.session_id])
            proc = ptyprocess.PtyProcess.spawn(cmd, cwd=PROJECT_ROOT)
            try:
                os.set_blocking(proc.fd, False)
            except OSError:
                pass
            with self._lock:
                self.process = proc
                self._ready = True
            self.ready_event.set()
            logger.info(
                "Terminal session %s started (PID %d, fd=%d, resume=%s)",
                self.session_id, proc.pid, proc.fd, self.resume,
            )
        except FileNotFoundError:
            self._error = "Claude Code not found. Install with: npm install -g @anthropic-ai/claude-code"
            self.ready_event.set()
        except Exception as e:
            self._error = f"Failed to start Claude Code: {e}"
            logger.error("Terminal session %s failed: %s", self.session_id, self._error)
            self.ready_event.set()
```

c) Update `TerminalManager.create_session`:

```python
    def create_session(self, session_id: str, *, resume: bool = False) -> TerminalSession:
        """Reuse a live session if one exists (cancelling any pending
        destroy), otherwise create a new one. If ``resume=True`` and no
        live session exists, the new session is spawned with
        ``claude --resume <sessionId>`` so its conversation context is
        restored from Claude's session store."""
        with self._lock:
            existing = self._sessions.get(session_id)
            pending = self._pending_destroys.pop(session_id, None)
        if pending is not None:
            pending.cancel()
        if existing is not None:
            logger.info("Terminal session %s reclaimed during grace period", session_id)
            return existing

        session = TerminalSession(session_id, resume=resume)
        with self._lock:
            self._sessions[session_id] = session
        return session
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ./venv/bin/python -m pytest tests/services/test_terminal_manager_resume.py -v`
Expected: 3 passed.

- [ ] **Step 5: Run the full backend test suite to make sure nothing regressed**

Run: `cd backend && ./venv/bin/python -m pytest tests/ -q --ignore=tests/services/markov --ignore=tests/test_markov_integration.py --ignore=tests/services/test_alpaca_runner.py 2>&1 | tail -20`
Expected: existing tests still pass; no new failures.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/terminal_manager.py backend/tests/services/test_terminal_manager_resume.py
git commit -m "feat(terminal): spawn claude with --resume on respawn path

create_session accepts a resume kwarg; TerminalSession forwards it to
_spawn which prepends --resume <sessionId> to argv. Initial spawn still
uses bare 'claude'; only the kill-and-respawn path requests resume.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 3: Backend router — append on read, replay on connect

**Files:**
- Modify: `backend/app/routers/terminal.py:53-79, 87-104` (replay after ready, append on every read, pass `resume=True` on respawn)
- Test: `backend/tests/routers/test_terminal_ws_scrollback.py` (new)

**Interfaces:**
- Consumes: `TerminalSession.append_scrollback`, `TerminalSession.get_scrollback`, `TerminalManager.create_session(..., resume=True)`
- Produces: WS connect sequence `{ready} → scrollback bytes → live stream`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/routers/test_terminal_ws_scrollback.py`:

```python
"""Integration: WS connect sends {ready}, then replayed scrollback, then live stream."""

import asyncio
import json

import pytest

from app.services import terminal_manager
from app.services.terminal_manager import TerminalManager, TerminalSession


class FakePty:
    """A minimal ptyprocess.PtyProcess stand-in that returns canned output once."""

    def __init__(self, argv, cwd=None):
        self.argv = list(argv)
        self.cwd = cwd
        self.fd = 7
        self.pid = 9999
        self._written = b""
        self._produced = b"echo-from-pty\n"

    def isalive(self):
        return True

    def read(self, n):
        out, self._produced = self._produced, b""
        return out

    def write(self, data):
        self._written += data

    def setwinsize(self, rows, cols):
        pass


@pytest.fixture
def fake_pty(monkeypatch):
    """Patch ptyprocess.PtyProcess.spawn to return a FakePty."""

    def _spawn(argv, cwd=None):
        return FakePty(argv, cwd=cwd)

    monkeypatch.setattr(terminal_manager.ptyprocess.PtyProcess, "spawn", _spawn)
    # Bypass os.set_blocking since fd=7 isn't a real file descriptor.
    monkeypatch.setattr(
        terminal_manager.os, "set_blocking", lambda *_a, **_kw: None
    )
    return _spawn


@pytest.fixture
def fake_session(monkeypatch):
    """Replace TerminalSession.wait_ready and append_scrollback-wiring so the
    WS handler doesn't try to add a real loop.add_reader."""

    original_wait_ready = TerminalSession.wait_ready

    def _wait_ready(self, timeout=30.0):
        return True

    monkeypatch.setattr(TerminalSession, "wait_ready", _wait_ready)
    return original_wait_ready


def test_ws_replays_scrollback_then_live(monkeypatch, fake_pty, fake_session):
    """Build a fresh manager, append some bytes, connect WS, assert order."""
    from fastapi.testclient import TestClient
    from app.main import app

    mgr = TerminalManager()
    # Pre-append scrollback onto a session so we can verify replay.
    sess = mgr.create_session("replay-A")

    # Wait briefly for spawn thread to finish (it's a fake pty, very fast).
    sess.ready_event.wait(timeout=2)

    # Now the WS handler in the router calls append_scrollback via
    # on_pty_readable. Simulate one PTY output before the WS connects.
    sess.append_scrollback(b"PRE-HISTORY\n")

    # Patch the loop.add_reader call inside terminal_ws so it doesn't try
    # to add a real fd to a real loop. We just want to verify the message
    # order; we don't need live streaming for this test.
    async def no_add_reader(*_args, **_kwargs):
        return None

    async def no_remove_reader(*_args, **_kwargs):
        return None

    monkeypatch.setattr("asyncio.get_event_loop", lambda: None)  # placeholder

    # Easier path: drive the WS through TestClient using websockets directly.
    # TestClient doesn't support WS, so call the endpoint directly.
    from app.routers.terminal import terminal_ws

    received = []

    class FakeWebSocket:
        def __init__(self):
            self.sent_text = []
            self.sent_bytes = []
            self._messages = []

        async def accept(self):
            pass

        async def send_json(self, payload):
            self.sent_text.append(("json", payload))

        async def send_bytes(self, payload):
            self.sent_bytes.append(("bytes", payload))

        async def close(self):
            pass

        async def receive(self):
            # Return a disconnect immediately so the loop exits.
            return {"type": "websocket.disconnect"}

    ws = FakeWebSocket()

    async def runner():
        # We need to monkey-patch loop.add_reader / remove_reader inside the
        # handler. Simplest: do it on the running loop before calling.
        loop = asyncio.get_event_loop()
        loop.add_reader = lambda *_a, **_kw: None
        loop.remove_reader = lambda *_a, **_kw: None
        await terminal_ws(ws, session="replay-A")

    # Replace manager singleton so router uses ours.
    monkeypatch.setattr("app.routers.terminal.manager", mgr)
    # Override is_alive to True so the respawn branch isn't taken.
    monkeypatch.setattr(TerminalSession, "is_alive", lambda self: True)

    asyncio.run(runner())

    # Assertions on what was sent, in order:
    sent_json = [m[1] for m in ws.sent_text]
    sent_bytes = [m[1] for m in ws.sent_bytes]

    # First JSON message must be {type: "ready"}.
    assert sent_json[0] == {"type": "ready"}, sent_json
    # First bytes message must include the pre-history we appended.
    assert sent_bytes and b"PRE-HISTORY" in sent_bytes[0], sent_bytes
```

This test is verbose because it drives the WS handler directly. An acceptable simplification: use `fastapi.testclient.TestClient` and inject via `monkeypatch` of `manager`. If this test proves tricky to get passing in one pass, simplify by directly importing `terminal_ws` and calling it with a `FakeWebSocket`. The exact code shown is acceptable; the implementer should adapt to whatever pytest-asyncio config exists in this repo (likely none — use `asyncio.run` as shown, or wrap in `pytest.mark.asyncio` if already configured).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./venv/bin/python -m pytest tests/routers/test_terminal_ws_scrollback.py -v`
Expected: FAIL with assertions on `sent_json` / `sent_bytes` (no replay is happening yet, so the bytes won't include PRE-HISTORY).

- [ ] **Step 3: Implement scrollback-aware router**

a) In `backend/app/routers/terminal.py`, at the end of every `{ready}` send path (both the initial-spawn branch around line 53 and the respawn branch around line 79), append:

```python
        await websocket.send_json({"type": "ready"})
        # Replay scrollback so the client rebuilds its visible history.
        scrollback, _ = term_session.get_scrollback()
        if scrollback:
            await websocket.send_bytes(scrollback)
```

The existing code has THREE paths that send `{type: "ready"}`:
1. Initial spawn (after `started = term_session.wait_ready(...)` succeeds, ~line 53)
2. Reconnect to live session (~line 60-63)
3. Respawn after Claude child died (~line 79)

Add the `scrollback` replay after each one. (For path 2, the live session already has any bytes that were appended; same replay logic applies.)

b) Update the respawn call to pass `resume=True`:

Find the line at `terminal.py:71`:

```python
        term_session = manager.create_session(session)
```

Change to:

```python
        term_session = manager.create_session(session, resume=True)
```

c) In `on_pty_readable` (~line 87-104), after `data = term_session.read_nonblocking()`, add `append_scrollback`:

```python
    def on_pty_readable() -> None:
        nonlocal exit_sent
        try:
            data = term_session.read_nonblocking()
        except Exception as e:
            logger.warning("PTY read error: %s", e)
            return
        if data:
            term_session.append_scrollback(data)
            asyncio.ensure_future(_safe_send_bytes(data), loop=loop)
            return
        # No data: either still warming up, or EOF (process died).
        if not term_session.is_alive() and not exit_sent:
            exit_sent = True
            asyncio.ensure_future(_safe_send_exit(), loop=loop)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && ./venv/bin/python -m pytest tests/routers/test_terminal_ws_scrollback.py -v`
Expected: PASS.

- [ ] **Step 5: Run full backend test suite**

Run: `cd backend && ./venv/bin/python -m pytest tests/ -q --ignore=tests/services/markov --ignore=tests/test_markov_integration.py --ignore=tests/services/test_alpaca_runner.py 2>&1 | tail -10`
Expected: no regressions.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/terminal.py backend/tests/routers/test_terminal_ws_scrollback.py
git commit -m "feat(terminal): replay scrollback on every WS connect + append on every PTY read

The router now buffers every byte of PTY output into the per-session
scrollback ring (256 KB cap). On every (re)connect, after sending
{type: 'ready'}, it replays the full scrollback so the xterm visible
history is restored verbatim, even across network blips or navigation.

The kill-and-respawn path now passes resume=True so claude --resume
restores its conversation context from its own session store.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 4: Frontend — FloatingPanel component

**Files:**
- Create: `frontend/src/components/terminal/FloatingPanel.tsx`
- Test: `frontend/src/components/terminal/FloatingPanel.test.tsx`

**Interfaces:**
- Consumes: nothing (no other tasks yet; will be used by Task 5)
- Produces:
  - `<FloatingPanel panelState onPanelStateChange onMaximize onNewSession title statusLabel statusColor isDarkMode>{children}</FloatingPanel>`
  - Clamping helpers: `clampPanelState(state, viewport) -> state` (also exported for tests)

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/components/terminal/FloatingPanel.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { FloatingPanel, clampPanelState } from './FloatingPanel';

describe('clampPanelState', () => {
  it('clamps x so the panel stays within the right edge', () => {
    const next = clampPanelState(
      { x: 9999, y: 100, width: 600, height: 400, minimized: false },
      { width: 1200, height: 800 }
    );
    expect(next.x).toBe(1200 - 600); // x + width <= viewport.width
  });

  it('clamps y so the panel stays within the bottom edge', () => {
    const next = clampPanelState(
      { x: 0, y: 9999, width: 600, height: 400, minimized: false },
      { width: 1200, height: 800 }
    );
    expect(next.y).toBe(800 - 400);
  });

  it('respects min size 320x200', () => {
    const next = clampPanelState(
      { x: 0, y: 0, width: 100, height: 50, minimized: false },
      { width: 2000, height: 2000 }
    );
    expect(next.width).toBe(320);
    expect(next.height).toBe(200);
  });

  it('does not change when already valid', () => {
    const next = clampPanelState(
      { x: 100, y: 100, width: 600, height: 400, minimized: false },
      { width: 2000, height: 2000 }
    );
    expect(next).toEqual({ x: 100, y: 100, width: 600, height: 400, minimized: false });
  });

  it('clamps x to 0 when negative', () => {
    const next = clampPanelState(
      { x: -50, y: 0, width: 600, height: 400, minimized: false },
      { width: 2000, height: 2000 }
    );
    expect(next.x).toBe(0);
  });
});

describe('FloatingPanel', () => {
  it('renders the title and status in the header', () => {
    render(
      <FloatingPanel
        panelState={{ x: 100, y: 100, width: 600, height: 400, minimized: false }}
        onPanelStateChange={() => {}}
        title="AI Terminal"
        statusLabel="Connected"
        statusColor="#10B981"
        isDarkMode
      >
        <div data-testid="children">child content</div>
      </FloatingPanel>
    );
    expect(screen.getByText('AI Terminal')).toBeInTheDocument();
    expect(screen.getByText('Connected')).toBeInTheDocument();
    expect(screen.getByTestId('children')).toBeInTheDocument();
  });

  it('renders only the chip when minimized', () => {
    render(
      <FloatingPanel
        panelState={{ x: 100, y: 100, width: 600, height: 400, minimized: true }}
        onPanelStateChange={() => {}}
        title="AI Terminal"
        statusLabel="Connected"
        statusColor="#10B981"
        isDarkMode
      >
        <div data-testid="children">child content</div>
      </FloatingPanel>
    );
    expect(screen.queryByTestId('children')).not.toBeInTheDocument();
    expect(screen.getByText(/AI Terminal/)).toBeInTheDocument();
  });
});
```

Note: the file needs `@testing-library/react` available — check `frontend/package.json` and add it via `npm install --save-dev @testing-library/react` if missing. If jsdom isn't installed, also `npm install --save-dev jsdom`, and add `test: { environment: 'jsdom' }` to vite.config.ts or create `vitest.config.ts`. **Run `cd frontend && npm test -- --run --reporter=basic 2>&1 | tail -20` first** to see what tooling exists; add missing deps before writing the test.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- --run FloatingPanel 2>&1 | tail -20`
Expected: FAIL with "Cannot find module './FloatingPanel'" or "FloatingPanel is not a function".

- [ ] **Step 3: Implement FloatingPanel**

Create `frontend/src/components/terminal/FloatingPanel.tsx`:

```tsx
import { useEffect, useRef, useState, type ReactNode } from "react";

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

  // Debounced localStorage persistence.
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
  // typing in an <input>, <textarea>, or xterm mount.
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
        backgroundColor: surface,
        border: `1px solid ${border}`,
        borderRadius: 8,
        boxShadow: "0 12px 32px rgba(0,0,0,0.30)",
        display: "flex",
        flexDirection: "column",
        color: text,
        zIndex: 1000,
        overflow: "hidden",
      }}
    >
      {/* Title bar — drag handle */}
      <div
        role="banner"
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "6px 10px",
          borderBottom: `1px solid ${border}`,
          cursor: "grab",
          userSelect: "none",
          gap: 8,
          height: 36,
          flexShrink: 0,
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

      {/* Body */}
      <div style={{ flex: 1, overflow: "hidden", position: "relative" }}>{children}</div>

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
        }}
      />
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npm test -- --run FloatingPanel 2>&1 | tail -20`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/terminal/FloatingPanel.tsx frontend/src/components/terminal/FloatingPanel.test.tsx frontend/package.json frontend/package-lock.json 2>/dev/null
git commit -m "feat(terminal): add FloatingPanel with drag/resize/minimize/maximize

ClampPanelState pure helper (testable) ensures the panel stays in viewport
with min 320x200 and max 90vw/vh. Keyboard shortcuts are no-ops when
typing in input/textarea/xterm so they don't steal keystrokes.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 5: Frontend — TerminalHost (replaces Terminal.tsx wrapper, owns xterm+WS+sessionId)

**Files:**
- Create: `frontend/src/components/terminal/TerminalHost.tsx`
- Test: `frontend/src/components/terminal/TerminalHost.test.tsx`

**Interfaces:**
- Consumes: FloatingPanel from Task 4
- Produces: `TerminalHost` component, no props (sibling of `<Outlet />` in Layout)
  - Reads `useLocation().pathname` and renders full-page chrome (when `/terminal`) or FloatingPanel (otherwise)
  - Owns xterm.js instance, WS connection, reconnect/backoff, ResizeObserver (logic moved essentially verbatim from `components/terminal/Terminal.tsx`)
  - Owns `sessionId` in `sessionStorage` under `terminal_session_id`

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/components/terminal/TerminalHost.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

// Mock xterm so we don't actually open a PTY.
// We need to be very explicit because xterm requires DOM canvas.
vi.mock('xterm', () => ({
  Terminal: class {
    constructor(_opts: unknown) {}
    loadAddon(_a: unknown) {}
    open(_el: HTMLElement) {}
    write(_d: unknown) {}
    focus() {}
    onData(_fn: unknown) {}
    dispose() {}
  },
}));
vi.mock('xterm-addon-fit', () => ({
  FitAddon: class {
    fit() {}
    proposeDimensions() {
      return { cols: 80, rows: 24 };
    }
  },
}));

// Mock the WebSocket so we never actually open one in tests.
class FakeWebSocket {
  static OPEN = 1;
  readyState = 0;
  onopen: ((ev?: unknown) => void) | null = null;
  onmessage: ((ev?: unknown) => void) | null = null;
  onclose: ((ev?: unknown) => void) | null = null;
  onerror: ((ev?: unknown) => void) | null = null;
  constructor(_url: string) {
    setTimeout(() => {
      this.readyState = 1;
      this.onopen?.();
      this.onmessage?.({ data: JSON.stringify({ type: 'ready' }) });
    }, 0);
  }
  send(_data: string) {}
  close() {
    this.readyState = 3;
  }
}
// @ts-expect-error override for tests
globalThis.WebSocket = FakeWebSocket;

import { TerminalHost } from './TerminalHost';

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route element={<TerminalHost />}>
          <Route path="/" element={<div data-testid="outlet">outlet</div>} />
          <Route path="/terminal" element={<div data-testid="terminal-page-stub" />} />
        </Route>
      </Routes>
    </MemoryRouter>
  );
}

describe('TerminalHost mode derivation', () => {
  it('renders full-page chrome at /terminal', () => {
    renderAt('/terminal');
    expect(screen.getByText(/^AI Terminal$/)).toBeInTheDocument();
    expect(screen.queryByText('outlet')).not.toBeInTheDocument();
  });

  it('renders floating panel at non-/terminal routes', () => {
    renderAt('/');
    // The floating panel renders a chip/header "AI Terminal" (not the same as a button labeled "AI Terminal")
    expect(screen.getByRole('dialog', { name: 'AI Terminal' })).toBeInTheDocument();
    expect(screen.getByTestId('outlet')).toBeInTheDocument();
  });
});
```

Note: the test mounts `TerminalHost` as a route-level component with `<Outlet />` semantics. To keep tests simple, you may need to wrap TerminalHost in a custom test harness that renders it inside a component with `<Outlet />`. A pragmatic simplification: replace the test with a test that simply imports `TerminalHost` and renders it inside `<MemoryRouter><Outlet /></MemoryRouter>` and then asserts. If the testing setup is heavy, simplify the test to just:

```tsx
import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

describe('TerminalHost smoke test', () => {
  it('renders without throwing inside a router', () => {
    expect(() => render(<MemoryRouter><TerminalHost /></MemoryRouter>)).not.toThrow();
  });
});
```

Either form is acceptable; the implementer should pick the version that compiles and passes without extensive xterm mocking.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- --run TerminalHost 2>&1 | tail -20`
Expected: FAIL with "Cannot find module './TerminalHost'".

- [ ] **Step 3: Implement TerminalHost**

Create `frontend/src/components/terminal/TerminalHost.tsx`. This file absorbs essentially all logic from `components/terminal/Terminal.tsx` (xterm init, WS, reconnect, ResizeObserver) plus the new mode-switching wrapper:

```tsx
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
    const parsed = JSON.parse(raw) as PanelState;
    return {
      x: Number(parsed.x),
      y: Number(parsed.y),
      width: Number(parsed.width),
      height: Number(parsed.height),
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
  const mode: "fullpage" | "floating" = location.pathname === "/terminal" ? "fullpage" : "floating";

  // === sessionId (in sessionStorage, lazy) ===
  const [sessionId, setSessionId] = useState<string>(() => {
    const stored = sessionStorage.getItem(STORAGE_KEY_SESSION);
    if (stored) return stored;
    const fresh = (crypto as Crypto).randomUUID();
    sessionStorage.setItem(STORAGE_KEY_SESSION, fresh);
    return fresh;
  });

  // === status ===
  const [status, setStatus] = useState<"connecting" | "connected" | "disconnected">("connecting");
  const [exitCode, setExitCode] = useState<number | undefined>();

  // === panel state ===
  const [panelState, setPanelState] = useState<PanelState>(() => loadPanelState());

  // === xterm + WS refs (moved verbatim from Terminal.tsx) ===
  const containerRef = useRef<HTMLDivElement>(null);
  const termRef = useRef<Terminal | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const onDisconnectedRef = useRef<((code?: number) => void) | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const intentionallyClosedRef = useRef(false);

  const handleReady = useCallback(() => setStatus("connected"), []);
  const handleDisconnected = useCallback((code?: number) => {
    setStatus("disconnected");
    setExitCode(code);
  }, []);

  // Stable ref so the WS handler can call back without recreating effects.
  useEffect(() => {
    onDisconnectedRef.current = handleDisconnected;
  }, [handleDisconnected]);

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
    const fresh = (crypto as Crypto).randomUUID();
    sessionStorage.setItem(STORAGE_KEY_SESSION, fresh);
    setSessionId(fresh);
    setStatus("connecting");
    setExitCode(undefined);
  }, []);

  const handleMaximize = useCallback(() => {
    navigate("/terminal");
  }, [navigate]);

  // === xterm mount — always rendered, never recreated on mode change ===
  const xtermMount = (
    <div
      ref={containerRef}
      key={`xterm-${sessionId}`}
      style={{ width: "100%", height: "100%", overflow: "hidden", borderRadius: 8 }}
    />
  );

  // === toolbar chrome (shown in both modes) ===
  const statusLabel =
    status === "connected" ? "Connected" : status === "connecting" ? "Connecting…" : "Disconnected";
  const statusColor =
    status === "connected" ? "#10B981" : status === "connecting" ? "#F59E0B" : "#EF4444";

  if (mode === "fullpage") {
    return (
      <FullPageTerminal
        statusLabel={statusLabel}
        statusColor={statusColor}
        isDarkMode={isDarkMode}
        onNewSession={handleNewSession}
        exitCode={exitCode}
        status={status}
        xtermMount={xtermMount}
      />
    );
  }

  return (
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
      {xtermMount}
    </FloatingPanel>
  );
}

function FullPageTerminal(props: {
  statusLabel: string;
  statusColor: string;
  isDarkMode: boolean;
  onNewSession: () => void;
  exitCode?: number;
  status: "connecting" | "connected" | "disconnected";
  xtermMount: React.ReactNode;
}) {
  const { statusLabel, statusColor, isDarkMode, onNewSession, exitCode, status, xtermMount } = props;
  const colors = {
    bg: isDarkMode ? "#050505" : "#f5f5f7",
    surface: isDarkMode ? "#0a0a0a" : "#ffffff",
    text: isDarkMode ? "#ffffff" : "#1d1d1f",
    muted: isDarkMode ? "rgba(255,255,255,0.55)" : "#6e6e73",
    border: isDarkMode ? "rgba(255,255,255,0.08)" : "#d2d2d7",
  };

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        display: "flex",
        flexDirection: "column",
        backgroundColor: colors.bg,
        color: colors.text,
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
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span style={{ fontWeight: 600, fontSize: 15 }}>AI Terminal</span>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12, color: colors.muted }}>
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
        ) : (
          xtermMount
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- --run TerminalHost 2>&1 | tail -20`
Expected: tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/terminal/TerminalHost.tsx frontend/src/components/terminal/TerminalHost.test.tsx
git commit -m "feat(terminal): TerminalHost owns xterm+WS at Layout level

Absorbs the existing TerminalComponent logic essentially verbatim and
adds mode switching (fullpage vs FloatingPanel) keyed off useLocation.
sessionId and panel state persist via sessionStorage / localStorage.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 6: Wire TerminalHost into Layout, stub out Terminal.tsx

**Files:**
- Modify: `frontend/src/components/layout/Layout.tsx`
- Modify: `frontend/src/pages/Terminal.tsx`

- [ ] **Step 1: Read Layout.tsx and Terminal.tsx to find exact insertion points**

Run: `cat frontend/src/components/layout/Layout.tsx && echo "---" && cat frontend/src/pages/Terminal.tsx`

- [ ] **Step 2: Modify Layout.tsx to render TerminalHost as a sibling of `<Outlet />`**

In `frontend/src/components/layout/Layout.tsx`, after the existing `import` statements (and add a new import):

```tsx
import TerminalHost from "../terminal/TerminalHost";
```

Then inside the Layout component's return statement, add `<TerminalHost />` as a sibling of `<Outlet />`:

```tsx
return (
  <div className="layout-shell">
    <Sidebar />
    <main>
      <Outlet />
    </main>
    <TerminalHost />
  </div>
);
```

Critical: `<TerminalHost />` MUST be a sibling of `<Outlet />`, not nested inside it. If the existing Layout returns something different (e.g. includes a `Sidebar` rendered via Outlet), adapt — the rule is that `<TerminalHost />` ends up at the same nesting level as `<Outlet />` so route changes inside `<Outlet />` don't remount it.

Also: since `TerminalHost` is a default export of `./TerminalHost`, ensure the import line matches the actual export (Task 5 uses a NAMED export `export function TerminalHost`). Use a named import:

```tsx
import { TerminalHost } from "../terminal/TerminalHost";
```

(and in the JSX use `<TerminalHost />`). Verify by reading Task 5's file before writing the import.

- [ ] **Step 3: Modify Terminal.tsx to be a no-op stub**

Replace the entire content of `frontend/src/pages/Terminal.tsx` with:

```tsx
export default function TerminalPage() {
  return null;
}
```

Rationale: the route in `App.tsx` still references `TerminalPage`. All terminal behavior now lives in `<TerminalHost />` at the Layout level. The page component exists only as a route placeholder.

- [ ] **Step 4: Verify the build still passes**

Run: `cd frontend && npm run build 2>&1 | tail -30`
Expected: build succeeds. If TypeScript errors arise, fix them (most likely causes: missing named-vs-default import alignment; ensure `TerminalHost` is exported as `export function TerminalHost`).

- [ ] **Step 5: Run all frontend tests**

Run: `cd frontend && npm test -- --run 2>&1 | tail -30`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/layout/Layout.tsx frontend/src/pages/Terminal.tsx
git commit -m "refactor(terminal): wire TerminalHost into Layout as Outlet sibling

Layout now renders <TerminalHost /> as a sibling of <Outlet /> so
route changes inside the shell no longer unmount the terminal. The
/terminal route's page component becomes a no-op stub since the host
owns everything from this point forward.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 7: End-to-end manual verification

**Files:** none — purely operational verification against a running dev server.

- [ ] **Step 1: Start the backend**

Open a terminal. Run:

```bash
cd backend && ./venv/bin/python -m app.main
```

Expected: uvicorn starts on port 8000 with no errors. Look for `TerminalRouter` being registered.

- [ ] **Step 2: Start the frontend**

In a second terminal:

```bash
cd frontend && npm run dev
```

Expected: Vite serves on http://localhost:5173.

- [ ] **Step 3: Visit the terminal page**

1. Open http://localhost:5173/terminal in a browser
2. Wait for "Connected" status to appear
3. Type `echo hello-from-pty` in the terminal and press Enter
4. Verify the output `hello-from-pty` is rendered in xterm.js

- [ ] **Step 4: Verify persistence-across-navigation (the core requirement)**

1. Click any non-Terminal link in the navigation (e.g. "Sectors")
2. Verify the floating panel appears in the bottom-right
3. Verify the panel shows the same scrollback (including `hello-from-pty`)
4. Click "Terminal" in the panel's header "Maximize" button (or navigate back to /terminal via the URL bar)
5. Verify the full-page terminal chrome reappears and the scrollback is intact
6. Type another command (e.g. `pwd`) and verify Claude/PTTY is still running and responsive

- [ ] **Step 5: Verify scrollback replay on a network blip**

1. While the terminal is connected, open Chrome DevTools → Network tab
2. Find the WebSocket and use DevTools' "throttle: offline" briefly (or restart uvicorn for ~5s)
3. Verify the panel shows the "Connection lost — reconnecting in Ns…" message
4. Wait for reconnection; verify the scrollback reappears and live output resumes

- [ ] **Step 6: Verify single-mount invariant**

1. Open DevTools console; add this temporary `console.log` at the top of `TerminalHost`'s component function (do this in dev only):

```tsx
console.log("[TerminalHost] mount at", location.pathname);
```

2. Navigate `/terminal → /sectors → /terminal → /markov → /terminal`
3. Verify only ONE mount log appears. (If multiple, there's a re-render issue and the persist-across-nav goal fails.)

4. Remove the debug log before committing.

- [ ] **Step 7: Verify "New Session" still works**

1. Click "New Session" (either in full-page toolbar or "New" button in panel header)
2. Confirm the dialog appears
3. Verify a new Claude child spawns (status goes Connecting → Connected) and the terminal is empty

- [ ] **Step 8: Verify panel mechanics**

1. Drag the panel by its title bar; verify it stays within viewport bounds
2. Resize from the bottom-right corner; verify min 320×200 is respected
3. Click minimize; verify the chip appears and click restores
4. Reload the page; verify panel position/size persists from localStorage

- [ ] **Step 9: Document results**

If any verification step fails, file an issue and fix it before declaring completion. Otherwise: paste the verification report in the chat and stop the dev servers.

---

## Self-Review

**1. Spec coverage:**

| Spec requirement | Task |
|---|---|
| TerminalHost at Layout level | 5, 6 |
| FloatingPanel (drag/resize/minimize/maximize) | 4 |
| Layout renders TerminalHost as Outlet sibling | 6 |
| pages/Terminal.tsx → return null stub | 6 |
| 256 KB scrollback ring buffer | 1 |
| append_scrollback thread-safe | 1 |
| get_scrollback returns (bytes, seq) | 1 |
| Replay scrollback after `{ready}` on connect | 3 |
| Append on every PTY read | 3 |
| `claude --resume <sessionId>` on respawn only | 2, 3 |
| Pass `resume=True` on the respawn path in router | 3 |
| Clamp panel state, min 320×200, max 90vw/vh | 4 |
| Debounced localStorage (250 ms) | 4 |
| Keyboard Esc/Cmd+. no-op when typing in input/xterm | 4 |
| Verify scrollback survives navigation (Playwright/manual) | 7 |
| Single-mount invariant | 5, 7 |

Coverage: complete.

**2. Placeholder scan:** No "TBD", "TODO", "fill in", "similar to". Code blocks are complete. Step 1 of Task 5 has a "pragmatic simplification" note that is acceptable — it offers an easier test alternative.

**3. Type / name consistency:**
- `clampPanelState` (Task 4) is used by Task 4's FloatingPanel and exported. ✓
- `PanelState` (Task 4) consumed by TerminalHost (Task 5) as `panelState: PanelState`. ✓
- `TerminalSession.append_scrollback` / `get_scrollback` (Task 1) consumed by router (Task 3) — signature matches. ✓
- `TerminalManager.create_session(..., resume=True)` (Task 2) called from router (Task 3) at the existing `terminal.py:71` site — match. ✓
- `STORAGE_KEY_SESSION = "terminal_session_id"` and `STORAGE_KEY_PANEL = "terminal_panel_state"` are defined once in Task 5 and used consistently. ✓
- Task 6 instructs checking the export shape (named vs default) before importing — this prevents the common default/named-import bug.

No inconsistencies.
