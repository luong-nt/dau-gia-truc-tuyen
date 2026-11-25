from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core.deps import CurrentUser, DbSession, require_roles
from app.db.enums import UserRole
from app.db.models import User
from app.modules.results import service
from app.modules.results.schemas import AdjustResultRequest, ConfirmResultRequest, ResultOut

router = APIRouter(prefix="/sessions/{session_id}/results", tags=["Kết quả đấu giá (FR-22, FR-23)"])
AuctioneerUser = Annotated[User, Depends(require_roles(UserRole.AUCTIONEER))]


@router.get("", response_model=list[ResultOut])
async def list_results(session_id: int, user: CurrentUser, db: DbSession) -> list[ResultOut]:
    """Nội bộ xem mọi phiên bản (dự thảo và đã xác nhận)."""
    return await service.list_results(db, session_id, user)


@router.post("/{result_id}/confirm", response_model=ResultOut)
async def confirm_result(
    session_id: int,
    result_id: int,
    data: ConfirmResultRequest,
    auctioneer: AuctioneerUser,
    db: DbSession,
) -> ResultOut:
    return await service.confirm_result(db, session_id, result_id, auctioneer, data)


@router.post("", response_model=ResultOut, status_code=status.HTTP_201_CREATED)
async def adjust_result(
    session_id: int,
    data: AdjustResultRequest,
    auctioneer: AuctioneerUser,
    db: DbSession,
) -> ResultOut:
    return await service.adjust_result(db, session_id, auctioneer, data)


# TODO(FR-23): GET  "/{result_id}/minutes"   Xuất biên bản PDF
