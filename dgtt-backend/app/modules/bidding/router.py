from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.deps import CurrentUser, DbSession, require_roles
from app.db.enums import UserRole
from app.db.models import User
from app.modules.bidding import service
from app.modules.bidding.schemas import BidOut, PlaceBidRequest, PublicBidOut, SessionStateOut

router = APIRouter(prefix="/sessions/{session_id}", tags=["Trả giá trực tuyến (FR-18 - FR-21)"])

BidderUser = Annotated[User, Depends(require_roles(UserRole.BIDDER))]


@router.post("/bids", response_model=BidOut)
async def place_bid(session_id: int, data: PlaceBidRequest, bidder: BidderUser, db: DbSession):
    """Gửi lệnh trả giá. Luôn trả kết quả ACCEPTED hoặc REJECTED kèm lý do (FR-18)."""
    return await service.place_bid(db, session_id, bidder, data)


@router.get("/state", response_model=SessionStateOut)
async def room_state(session_id: int, user: CurrentUser, db: DbSession):
    """Ảnh chụp trạng thái phòng, gọi khi vào phòng hoặc kết nối lại (FR-19)."""
    return await service.get_room_state(db, session_id, user)


@router.get("/bids", response_model=list[PublicBidOut])
async def bid_history(
    session_id: int,
    user: CurrentUser,
    db: DbSession,
    include_rejected: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return await service.list_bid_history(
        db, session_id, user, include_rejected=include_rejected, limit=limit, offset=offset
    )
