"""WebSocket terminal router — streams Claude Code CLI to the browser."""

import json
import logging
import asyncio
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

    logger.info("WebSocket connected: session=%s", session)

    async def read_pty():
        """Background task: poll PTY stdout and send to WebSocket."""
        while True:
            try:
                data = term_session.read()
                if data:
                    await websocket.send_bytes(data)
                elif not term_session.is_alive():
                    await websocket.send_json({
                        "type": "exit",
                        "code": -1,
                    })
                    break
                else:
                    await asyncio.sleep(0.05)
            except Exception:
                break

    read_task = asyncio.create_task(read_pty())

    try:
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
        read_task.cancel()
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
