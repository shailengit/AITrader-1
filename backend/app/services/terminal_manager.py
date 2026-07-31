"""PTY-based terminal session manager for the web terminal.

Spawns a Claude Code process inside a pseudo-terminal and manages
its lifecycle. One session per WebSocket connection.
"""

import os
import errno
import logging
import time
import threading
from collections import deque
from typing import Optional
import ptyprocess

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)


class TerminalSession:
    """A single Claude Code process running inside a PTY.

    The process is spawned in a background thread so it doesn't block
    the asyncio event loop. Poll `is_ready()` or wait for `ready_event`
    to know when the process has started.

    The master PTY fd is set non-blocking so callers can poll it from
    asyncio's event loop via `loop.add_reader()` without freezing the
    loop. Use `read_nonblocking()` (returns ``b""`` if no data is
    available instead of blocking).

    Each session also maintains a bounded ring buffer of the most recent
    PTY output (``SCROLLBACK_MAX_BYTES``). The router replays this
    buffer to the client on every WebSocket connect so the user-visible
    scrollback is restored after navigation or a transient disconnect.
    """

    SCROLLBACK_MAX_BYTES = 256 * 1024  # 256 KB cap

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

        # Scrollback ring buffer for replay on (re)connect.
        self._scrollback: deque[bytes] = deque()
        self._scrollback_bytes = 0
        self._scrollback_seq = 0
        self._scrollback_lock = threading.Lock()

        # Start spawn in background thread
        self._spawn_thread = threading.Thread(target=self._spawn, daemon=True)
        self._spawn_thread.start()

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
            # Put the master fd in non-blocking mode so callers can poll
            # it from asyncio's event loop without freezing the loop.
            try:
                os.set_blocking(proc.fd, False)
            except OSError:
                # Some platforms may not support this — ignore.
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

    @property
    def is_ready(self) -> bool:
        return self._ready

    @property
    def error(self) -> Optional[str]:
        return self._error

    def wait_ready(self, timeout: float = 30.0) -> bool:
        """Wait for the process to start. Returns True if ready, False if timeout."""
        return self.ready_event.wait(timeout=timeout)

    def fileno(self) -> int:
        """Return the master PTY fd for use with loop.add_reader()."""
        with self._lock:
            if self.process is None:
                raise OSError(errno.EBADF, "Process not started")
            return self.process.fd

    def read_nonblocking(self) -> bytes:
        """Non-blocking read from the PTY master.

        Returns ``b""`` if no data is available (the caller should wait
        for the fd to become readable again). Returns ``b""`` on EOF
        (Linux EIO and BSD empty-string both normalized here).
        """
        with self._lock:
            proc = self.process
            if proc is None:
                return b""
            try:
                self.last_activity = time.time()
                return proc.read(4096)
            except OSError as e:
                if e.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                    return b""
                if e.errno == errno.EIO:
                    # Linux EOF on PTY — child closed its side.
                    return b""
                raise
            except EOFError:
                return b""

    def write(self, data) -> None:
        """Write data to the PTY's stdin.

        Accepts ``str`` (encoded as UTF-8) or ``bytes``. Best-effort:
        if the PTY is closed, the call is silently ignored.
        """
        if isinstance(data, str):
            data = data.encode("utf-8", errors="replace")
        with self._lock:
            if self.process and self._alive_unlocked():
                try:
                    self.process.write(data)
                    self.last_activity = time.time()
                except (OSError, TypeError, ValueError):
                    # PTY closed or bad input — treat as no-op.
                    pass

    def resize(self, cols: int, rows: int) -> None:
        """Resize the PTY terminal dimensions."""
        with self._lock:
            if self.process and self._alive_unlocked():
                try:
                    self.process.setwinsize(rows, cols)
                except Exception:
                    pass

    def kill(self) -> None:
        """Terminate the Claude Code process.

        Close the master fd first so any reader on it gets EBADF and
        returns immediately, then force-terminate the child.
        """
        with self._lock:
            if self.process:
                # Closing the master fd from this thread unblocks any
                # other thread that's currently parked in read() on it.
                try:
                    if (
                        self.process.fd is not None
                        and self.process.fd >= 0
                    ):
                        os.close(self.process.fd)
                except OSError:
                    pass
                self.process.fd = -1
                try:
                    self.process.close(force=True)
                except Exception:
                    try:
                        self.process.terminate(force=True)
                    except Exception:
                        pass
                self.process = None
                logger.info("Terminal session %s killed", self.session_id)

    def _alive_unlocked(self) -> bool:
        """Check if alive (caller must hold _lock)."""
        if self.process is None:
            return False
        try:
            return self.process.isalive()
        except Exception:
            return False

    def is_alive(self) -> bool:
        """Check if the Claude Code process is still running."""
        with self._lock:
            return self._alive_unlocked()

    def append_scrollback(self, chunk: bytes) -> None:
        """Append PTY output to the scrollback ring buffer. Trims oldest
        bytes when over ``SCROLLBACK_MAX_BYTES``. Thread-safe."""
        if not chunk:
            return
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
        """Return ``(concat_scrollback, current_seq)``.

        ``current_seq`` is monotonic and increments once per
        ``append_scrollback`` call. The current router always replays
        the full buffer; the seq is exposed for future incremental
        replay without changing the API.
        """
        with self._scrollback_lock:
            return b"".join(self._scrollback), self._scrollback_seq

    @property
    def idle_seconds(self) -> float:
        return time.time() - self.last_activity


class TerminalManager:
    """Manages all active terminal sessions.

    Sessions are not destroyed immediately when the WebSocket disconnects
    — there is a grace period (``destroy_grace_seconds``) during which
    a reconnecting client can claim the existing session. This handles
    React StrictMode double-mounts, transient network blips, and page
    navigation without losing the spawned Claude Code child.
    """

    destroy_grace_seconds: float = 3600.0

    def __init__(self):
        self._sessions: dict[str, TerminalSession] = {}
        self._pending_destroys: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def create_session(self, session_id: str, *, resume: bool = False) -> TerminalSession:
        """Reuse a live session if one exists (cancelling any pending
        destroy), otherwise create a new one.

        If ``resume=True`` and no live session exists, the new session
        is spawned with ``claude --resume <sessionId>`` so its
        conversation context is restored from Claude's session store.
        """
        with self._lock:
            existing = self._sessions.get(session_id)
            pending = self._pending_destroys.pop(session_id, None)
        if pending is not None:
            pending.cancel()
        if existing is not None:
            # Reclaim the existing session.
            logger.info("Terminal session %s reclaimed during grace period", session_id)
            return existing

        # No existing session — create a new one.
        session = TerminalSession(session_id, resume=resume)
        with self._lock:
            self._sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[TerminalSession]:
        with self._lock:
            return self._sessions.get(session_id)

    def cancel_pending_destroy(self, session_id: str) -> None:
        """Cancel any scheduled destroy for this session.

        Used by the router when a client reconnects to a session that
        was marked for destruction during a transient disconnect.
        """
        self._cancel_pending_destroy(session_id)

    def destroy_session(self, session_id: str) -> None:
        """Schedule a session for destruction after a short grace period.

        The session remains in ``_sessions`` and is still returned by
        ``get_session`` / reused by ``create_session`` until the grace
        period elapses. ``create_session`` cancels the pending destroy
        if it is called for the same ID; otherwise the timer fires and
        the session is removed and its Claude child killed.
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                # No live session — nothing to do. (A pending destroy
                # for an already-killed session is harmless.)
                return
            # Cancel any prior pending destroy (defensive — should
            # never happen, but guards against double-scheduling).
            prior = self._pending_destroys.pop(session_id, None)
        if prior is not None:
            prior.cancel()

        timer = threading.Timer(
            self.destroy_grace_seconds,
            self._finalize_destroy,
            args=(session_id, session),
        )
        timer.daemon = True
        with self._lock:
            self._pending_destroys[session_id] = timer
        timer.start()
        logger.info(
            "Terminal session %s scheduled for destroy in %.1fs (reclaimable)",
            session_id, self.destroy_grace_seconds,
        )

    def _finalize_destroy(self, session_id: str, session: TerminalSession) -> None:
        """Actually kill the session if it hasn't been reclaimed."""
        with self._lock:
            current = self._pending_destroys.get(session_id)
            # If a newer pending destroy exists, leave it alone.
            if current is None:
                return
            self._pending_destroys.pop(session_id, None)
            # Only remove the session from the live map if it's still
            # the same one (i.e. nobody reclaimed or replaced it).
            if self._sessions.get(session_id) is session:
                self._sessions.pop(session_id, None)
        try:
            session.kill()
        except Exception as e:
            logger.warning("Error killing session %s: %s", session_id, e)

    def _cancel_pending_destroy(self, session_id: str) -> None:
        with self._lock:
            timer = self._pending_destroys.pop(session_id, None)
        if timer is not None:
            timer.cancel()

    def cleanup_idle(self, timeout: int = 1800) -> int:
        """Kill sessions idle for more than `timeout` seconds. Returns count killed."""
        now = time.time()
        killed = 0
        with self._lock:
            for sid, session in list(self._sessions.items()):
                if now - session.last_activity > timeout:
                    logger.info("Cleaning up idle session %s", sid)
                    session.kill()
                    del self._sessions[sid]
                    killed += 1
        return killed


# Module-level singleton
manager = TerminalManager()
