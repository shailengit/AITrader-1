"""WebSocket terminal router — streams Claude Code CLI to the browser."""

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
    """
    await websocket.accept()

    if not session:
        await websocket.send_json({"type": "error", "message": "session parameter required"})
        await websocket.close()
        return

    import asyncio

    # Get or create session (spawn Claude Code in background to avoid blocking)
    term_session = manager.get_session(session)
    if term_session is None:
        await websocket.send_json({"type": "info", "message": "Starting Claude Code session..."})
        try:
            # Run the blocking spawn in a thread to not block the event loop
            loop = asyncio.get_event_loop()
            term_session = await loop.run_in_executor(None, lambda: manager.create_session(session))
            await websocket.send_json({"type": "ready"})
        except RuntimeError as e:
            await websocket.send_json({"type": "error", "message": str(e)})
            await websocket.close()
            return

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
                        "code": term_session.process.exitstatus if term_session.process else -1,
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
