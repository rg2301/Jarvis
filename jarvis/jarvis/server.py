"""FastAPI + WebSocket bridge between the Jarvis core and the browser HUD.

Runs on its own thread with its own asyncio loop. The EventBus is bound to
that loop so synchronous code anywhere in Jarvis can call `bus.emit(...)`
and the message gets shipped to every connected browser.
"""

from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path

try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles
    import uvicorn
except ImportError as e:
    raise SystemExit(
        f"[ERROR] Missing dependency: {e}. "
        "Run: pip install fastapi uvicorn websockets"
    )

from .config import log
from .events import bus

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


def build_app() -> FastAPI:
    app = FastAPI(title="J.A.R.V.I.S HUD")

    @app.get("/")
    async def root():
        return FileResponse(WEB_DIR / "index.html")

    if WEB_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")

    @app.websocket("/ws")
    async def ws(socket: WebSocket):
        await socket.accept()
        queue: asyncio.Queue[dict] = asyncio.Queue()

        async def push(msg: dict) -> None:
            await queue.put(msg)

        bus.subscribe(push)
        await socket.send_text(json.dumps({"type": "hello"}))

        try:
            while True:
                msg = await queue.get()
                await socket.send_text(json.dumps(msg, default=str))
        except WebSocketDisconnect:
            pass
        except Exception as e:
            log.warning(f"WS error: {e}")
        finally:
            bus.unsubscribe(push)

    return app


def start_in_background(host: str = "127.0.0.1", port: int = 8765) -> None:
    """Spawn the HUD server in a daemon thread and bind the EventBus to its loop."""
    ready = threading.Event()

    def _run() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        bus.attach_loop(loop)

        config = uvicorn.Config(
            build_app(),
            host=host,
            port=port,
            log_level="warning",
            loop="asyncio",
        )
        server = uvicorn.Server(config)
        ready.set()
        loop.run_until_complete(server.serve())

    threading.Thread(target=_run, daemon=True, name="jarvis-hud").start()
    ready.wait(timeout=5)

    # Background data feeders for the HUD.
    from .monitors import start_all
    start_all()

    log.info(f"HUD server listening on http://{host}:{port}")
