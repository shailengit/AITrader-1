"""PTY-based terminal session manager for the web terminal.

Spawns a Claude Code process inside a pseudo-terminal and manages
its lifecycle. One session per WebSocket connection.
"""

import os
import logging
import time
import threading
import ptyprocess
from typing import Optional

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)


class TerminalSession:
    """A single Claude Code process running inside a PTY.

    The process is spawned in a background thread so it doesn't block
    the asyncio event loop. Poll `is_ready()` or wait for `ready_event`
    to know when the process has started.
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.process: Optional[ptyprocess.PtyProcess] = None
        self.last_activity = time.time()
        self.created_at = time.time()
        self._error: Optional[str] = None
        self._ready = False
        self.ready_event = threading.Event()
        self._lock = threading.Lock()

        # Start spawn in background thread
        self._spawn_thread = threading.Thread(target=self._spawn, daemon=True)
        self._spawn_thread.start()

    def _spawn(self):
        """Spawn Claude Code inside a pseudo-terminal (runs in background thread)."""
        try:
            proc = ptyprocess.PtyProcess.spawn(
                ["claude"],
                cwd=PROJECT_ROOT,
            )
            with self._lock:
                self.process = proc
                self._ready = True
            self.ready_event.set()
            logger.info("Terminal session %s started (PID %d)", self.session_id, proc.pid)
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

    def write(self, data: str) -> None:
        """Write data to the PTY's stdin."""
        with self._lock:
            if self.process and self._alive_unlocked():
                self.process.write(data)
                self.last_activity = time.time()

    def read(self) -> bytes:
        """Read from the PTY's stdout (non-blocking). Returns empty bytes if nothing available."""
        with self._lock:
            if not self.process or not self._alive_unlocked():
                return b""
            try:
                self.last_activity = time.time()
                return self.process.read(4096)
            except Exception:
                return b""

    def resize(self, cols: int, rows: int) -> None:
        """Resize the PTY terminal dimensions."""
        with self._lock:
            if self.process and self._alive_unlocked():
                try:
                    self.process.setwinsize(rows, cols)
                except Exception:
                    pass

    def kill(self) -> None:
        """Terminate the Claude Code process."""
        with self._lock:
            if self.process:
                try:
                    self.process.close()
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

    @property
    def idle_seconds(self) -> float:
        return time.time() - self.last_activity


class TerminalManager:
    """Manages all active terminal sessions."""

    def __init__(self):
        self._sessions: dict[str, TerminalSession] = {}
        self._lock = threading.Lock()

    def create_session(self, session_id: str) -> TerminalSession:
        """Create a new terminal session. Destroys existing one with same ID if any."""
        self.destroy_session(session_id)
        session = TerminalSession(session_id)
        with self._lock:
            self._sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[TerminalSession]:
        with self._lock:
            return self._sessions.get(session_id)

    def destroy_session(self, session_id: str) -> None:
        """Kill and remove a session."""
        with self._lock:
            session = self._sessions.pop(session_id, None)
        if session:
            session.kill()

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
