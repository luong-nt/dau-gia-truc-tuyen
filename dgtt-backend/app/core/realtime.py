"""Quản lý kết nối WebSocket theo phòng đấu giá (FR-19, NFR-02).

Lưu trong bộ nhớ tiến trình => backend phải chạy 1 worker.
Chỉ gọi `broadcast` SAU KHI đã commit transaction.
"""

import logging
from collections import defaultdict
from typing import Any

from fastapi import WebSocket
from fastapi.encoders import jsonable_encoder

from app.core.clock import utcnow

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self._rooms: dict[int, set[WebSocket]] = defaultdict(set)

    async def connect(self, session_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        self._rooms[session_id].add(websocket)

    def disconnect(self, session_id: int, websocket: WebSocket) -> None:
        room = self._rooms.get(session_id)
        if room is None:
            return
        room.discard(websocket)
        if not room:
            self._rooms.pop(session_id, None)

    def room_size(self, session_id: int) -> int:
        return len(self._rooms.get(session_id, ()))

    async def broadcast(self, session_id: int, event: str, data: dict[str, Any]) -> None:
        message = jsonable_encoder({"event": event, "server_time": utcnow(), "data": data})
        dead: list[WebSocket] = []
        for ws in list(self._rooms.get(session_id, ())):
            try:
                await ws.send_json(message)
            except Exception:  # kết nối đã đóng
                dead.append(ws)
        for ws in dead:
            self.disconnect(session_id, ws)


manager = ConnectionManager()


# Tên sự kiện dùng thống nhất giữa backend và frontend
EVENT_SNAPSHOT = "session.snapshot"
EVENT_BID_ACCEPTED = "bid.accepted"
EVENT_STATUS_CHANGED = "session.status_changed"
