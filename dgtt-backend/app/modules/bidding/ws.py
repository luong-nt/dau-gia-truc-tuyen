"""Kênh WebSocket của phòng đấu giá: ws://<host>/ws/sessions/{session_id}?token=<JWT>

- Khi kết nối: kiểm tra token và quyền vào phòng, gửi ngay sự kiện `session.snapshot`.
- Sau đó server đẩy `bid.accepted`, `session.status_changed`.
- Lệnh trả giá vẫn gửi qua REST (POST /api/v1/sessions/{id}/bids) để có phản hồi rõ ràng.
- Client gửi "ping" định kỳ, server trả "pong".
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from fastapi.encoders import jsonable_encoder

from app.core.deps import authenticate_token
from app.core.exceptions import AppError
from app.core.realtime import EVENT_SNAPSHOT, manager
from app.db.session import SessionLocal
from app.modules.bidding.service import get_room_state

router = APIRouter()


def _short(text: str) -> str:
    """Lý do đóng WebSocket tối đa 123 byte UTF-8."""
    return text.encode("utf-8")[:120].decode("utf-8", errors="ignore")


@router.websocket("/ws/sessions/{session_id}")
async def auction_room(websocket: WebSocket, session_id: int, token: str | None = None):
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Thiếu token")
        return

    try:
        async with SessionLocal() as db:
            user = await authenticate_token(db, token)
            snapshot = await get_room_state(db, session_id, user)
    except AppError as exc:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason=_short(exc.message))
        return

    await manager.connect(session_id, websocket)
    try:
        await websocket.send_json(jsonable_encoder({"event": EVENT_SNAPSHOT, "data": snapshot.model_dump()}))
        while True:
            message = await websocket.receive_text()
            if message == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(session_id, websocket)
