"""WebSocket terminal router — streams Claude Code CLI to the browser."""

import asyncio
import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services.terminal_manager import manager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/terminal/ws")
async def terminal_ws(websocket: WebSocket, session: str = ""):
    """WebSocket endpoint that wraps a Claude Code PTY session.

    Each connection gets its own Claude Code process. The session
    parameter allows reconnection to an existing session within the
    idle timeout window.

    PTY I/O is wired to asyncio via ``loop.add_reader()`` so the
    master fd wakes the event loop when data is available, instead of
    blocking the loop in a synchronous ``read()`` syscall.
    """
    await websocket.accept()

    if not session:
        await websocket.send_json({"type": "error", "message": "session parameter required"})
        await websocket.close()
        return

    # Get or create session (spawns Claude Code in a background thread)
    term_session = manager.get_session(session)
    if term_session is None:
        await websocket.send_json({"type": "info", "message": "Starting Claude Code session..."})
        term_session = manager.create_session(session)

        # Wait for the process to start (up to 30s)
        started = term_session.wait_ready(timeout=30.0)
        if not started:
            await websocket.send_json({"type": "error", "message": "Timed out waiting for Claude Code to start"})
            await websocket.close()
            manager.destroy_session(session)
            return

        if term_session.error:
            await websocket.send_json({"type": "error", "message": term_session.error})
            await websocket.close()
            manager.destroy_session(session)
            return

        await websocket.send_json({"type": "ready"})
    else:
        # Reconnecting to an existing session — cancel any pending
        # destroy (StrictMode double-mount / transient blip) and tell
        # the client we're already attached.
        manager.cancel_pending_destroy(session)
        if term_session.is_alive():
            await websocket.send_json({
                "type": "ready",
                "reconnected": True,
            })
        else:
            # Session exists but its Claude child has died (e.g. user
            # exited Claude). Recreate with the same ID.
            await websocket.send_json({
                "type": "info",
                "message": "Previous session ended. Starting new Claude Code session...",
            })
            term_session = manager.create_session(session)
            started = term_session.wait_ready(timeout=30.0)
            if not started or term_session.error:
                msg = term_session.error or "Timed out waiting for Claude Code to start"
                await websocket.send_json({"type": "error", "message": msg})
                await websocket.close()
                manager.destroy_session(session)
                return
            await websocket.send_json({"type": "ready"})

    logger.info("WebSocket connected: session=%s", session)

    loop = asyncio.get_running_loop()
    reader_attached = False
    exit_sent = False

    def on_pty_readable() -> None:
        """Called by the event loop when the PTY master fd has data.

        Runs on the event loop thread, so it's safe to call
        ``websocket.send_*`` here. Uses non-blocking read so it
        returns immediately if there's only a partial chunk.
        """
        nonlocal exit_sent
        try:
            data = term_session.read_nonblocking()
        except Exception as e:
            logger.warning("PTY read error: %s", e)
            return
        if data:
            # Schedule send on the loop to avoid awaiting inside the
            # synchronous reader callback.
            asyncio.ensure_future(_safe_send_bytes(data), loop=loop)
            return
        # No data: either still warming up, or EOF (process died).
        if not term_session.is_alive() and not exit_sent:
            exit_sent = True
            asyncio.ensure_future(_safe_send_exit(), loop=loop)

    async def _safe_send_bytes(data: bytes) -> None:
        try:
            await websocket.send_bytes(data)
        except Exception:
            pass

    async def _safe_send_exit() -> None:
        try:
            await websocket.send_json({"type": "exit", "code": -1})
        except Exception:
            pass

    try:
        try:
            fd = term_session.fileno()
        except OSError as e:
            await websocket.send_json({"type": "error", "message": str(e)})
            await websocket.close()
            manager.destroy_session(session)
            return

        loop.add_reader(fd, on_pty_readable)
        reader_attached = True

        while True:
            message = await websocket.receive()

            if message["type"] == "websocket.disconnect":
                break

            if message["type"] == "websocket.receive":
                raw = message.get("text") or message.get("bytes")
                if raw is None:
                    continue

                # Handle JSON control messages
                if isinstance(raw, str) and raw.startswith("{"):
                    try:
                        control = json.loads(raw)
                        if control.get("type") == "resize":
                            term_session.resize(control["cols"], control["rows"])
                            continue
                    except json.JSONDecodeError:
                        pass

                # Forward keystrokes to the PTY
                if isinstance(raw, str):
                    term_session.write(raw)
                elif isinstance(raw, bytes):
                    term_session.write(raw.decode("utf-8", errors="replace"))

    except WebSocketDisconnect:
        pass
    finally:
        if reader_attached:
            try:
                loop.remove_reader(fd)
            except (OSError, ValueError, Exception):
                pass
        manager.destroy_session(session)
        logger.info("WebSocket disconnected: session=%s", session)


@router.get("/terminal/health")
async def terminal_health():
    """Check if Claude Code is available."""
    import subprocess
    try:
        result = subprocess.run(
            ["claude", "--version"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return {"available": True, "version": result.stdout.strip()}
        return {"available": False, "error": result.stderr.strip()}
    except FileNotFoundError:
        return {"available": False, "error": "Claude Code not found. Install with: npm install -g @anthropic-ai/claude-code"}
    except Exception as e:
        return {"available": False, "error": str(e)}
