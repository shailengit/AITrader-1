"""PTY-based terminal session manager for the web terminal.

Spawns a Claude Code process inside a pseudo-terminal and manages
its lifecycle. One session per WebSocket connection.
"""

import os
import logging
import time
import ptyprocess
from typing import Optional

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)


class TerminalSession:
    """A single Claude Code process running inside a PTY."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.process: Optional[ptyprocess.PtyProcess] = None
        self.last_activity = time.time()
        self.created_at = time.time()

    def start(self):
        """Spawn Claude Code inside a pseudo-terminal."""
        try:
            self.process = ptyprocess.PtyProcess.spawn(
                ["claude"],
                cwd=PROJECT_ROOT,
            )
            logger.info("Terminal session %s started (PID %d)", self.session_id, self.process.pid)
        except FileNotFoundError:
            raise RuntimeError(
                "Claude Code not found. Install with: "
                "npm install -g @anthropic-ai/claude-code"
            )

    def write(self, data: str) -> None:
        """Write data to the PTY's stdin."""
        if self.process and self.is_alive():
            self.process.write(data)
            self.last_activity = time.time()

    def read(self) -> bytes:
        """Read from the PTY's stdout (non-blocking). Returns empty bytes if nothing available."""
        if not self.process or not self.is_alive():
            return b""
        try:
            self.last_activity = time.time()
            return self.process.read(4096)
        except Exception:
            return b""

    def resize(self, cols: int, rows: int) -> None:
        """Resize the PTY terminal dimensions."""
        if self.process and self.is_alive():
            try:
                self.process.setwinsize(rows, cols)
            except Exception:
                pass

    def kill(self) -> None:
        """Terminate the Claude Code process."""
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

    def is_alive(self) -> bool:
        """Check if the Claude Code process is still running."""
        if self.process is None:
            return False
        try:
            return self.process.isalive()
        except Exception:
            return False

    @property
    def idle_seconds(self) -> float:
        return time.time() - self.last_activity


class TerminalManager:
    """Manages all active terminal sessions."""

    def __init__(self):
        self._sessions: dict[str, TerminalSession] = {}

    def create_session(self, session_id: str) -> TerminalSession:
        """Create a new terminal session. Destroys existing one with same ID if any."""
        self.destroy_session(session_id)
        session = TerminalSession(session_id)
        session.start()
        self._sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[TerminalSession]:
        return self._sessions.get(session_id)

    def destroy_session(self, session_id: str) -> None:
        """Kill and remove a session."""
        session = self._sessions.pop(session_id, None)
        if session:
            session.kill()

    def cleanup_idle(self, timeout: int = 1800) -> int:
        """Kill sessions idle for more than `timeout` seconds. Returns count killed."""
        now = time.time()
        killed = 0
        for sid, session in list(self._sessions.items()):
            if now - session.last_activity > timeout:
                logger.info("Cleaning up idle session %s", sid)
                session.kill()
                del self._sessions[sid]
                killed += 1
        return killed


# Module-level singleton
manager = TerminalManager()
