"""Lightweight pub/sub bus that core modules emit to and the HUD listens on.

Runs on a background asyncio loop so synchronous code (the main Jarvis loop)
can fire events without blocking. Subscribers are coroutines (the WebSocket
handlers in server.py).
"""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Any, Callable, Coroutine


class EventBus:
    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._subscribers: set[Callable[[dict], Coroutine[Any, Any, None]]] = set()
        self._lock = threading.Lock()

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self, fn: Callable[[dict], Coroutine[Any, Any, None]]) -> None:
        with self._lock:
            self._subscribers.add(fn)

    def unsubscribe(self, fn: Callable[[dict], Coroutine[Any, Any, None]]) -> None:
        with self._lock:
            self._subscribers.discard(fn)

    def emit(self, kind: str, **payload: Any) -> None:
        """Fire-and-forget from any thread."""
        if self._loop is None:
            return
        msg = {"type": kind, "ts": time.time(), **payload}
        with self._lock:
            subs = list(self._subscribers)
        for fn in subs:
            try:
                asyncio.run_coroutine_threadsafe(fn(msg), self._loop)
            except Exception:
                pass


bus = EventBus()
