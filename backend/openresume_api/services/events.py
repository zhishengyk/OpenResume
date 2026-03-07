from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime


class EventBus:
    def __init__(self) -> None:
        self._history: dict[str, list[dict]] = defaultdict(list)
        self._subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)

    def publish(self, session_id: str, event_type: str, message: str, payload: dict | None = None) -> None:
        event = {
            "type": event_type,
            "session_id": session_id,
            "message": message,
            "timestamp": datetime.utcnow().isoformat(),
            "payload": payload or {},
        }
        self._history[session_id].append(event)
        for queue in self._subscribers[session_id]:
            queue.put_nowait(event)

    def history(self, session_id: str) -> list[dict]:
        return self._history[session_id]

    async def stream(self, session_id: str):
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers[session_id].append(queue)
        try:
            for event in self._history[session_id]:
                yield event

            while True:
                yield await queue.get()
        finally:
            self._subscribers[session_id].remove(queue)


event_bus = EventBus()
