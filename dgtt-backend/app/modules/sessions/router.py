from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core.deps import DbSession, OptionalUser, require_roles
from app.core.pagination import Page, Pagination
from app.db.enums import SessionStatus, UserRole
from app.db.models import User
from app.modules.sessions import service
from app.modules.sessions.schemas import (
    SessionCreateRequest,
    SessionOut,
    SessionPublicOut,
    SessionUpdateRequest,
    StatusChangeRequest,
)

router = APIRouter(prefix="/sessions", tags=["Phiên đấu giá (FR-08, FR-09, FR-16, FR-17)"])

StaffUser = Annotated[User, Depends(require_roles(UserRole.STAFF))]
AuctioneerUser = Annotated[User, Depends(require_roles(UserRole.AUCTIONEER))]
StaffOrAuctioneer = Annotated[User, Depends(require_roles(UserRole.STAFF, UserRole.AUCTIONEER))]

ManagerUser = Annotated[User, Depends(require_roles(UserRole.STAFF, UserRole.ADMIN, UserRole.AUCTIONEER))]


@router.get("", response_model=Page[SessionPublicOut])
async def list_public_sessions(
    db: DbSession,
    page: Pagination,
    status: SessionStatus | None = None,
    keyword: str | None = None,
) -> Page[SessionPublicOut]:
    return await service.list_sessions(db, status=status, keyword=keyword, page=page)


@router.get("/manage", response_model=Page[SessionPublicOut])
async def list_managed_sessions(
    db: DbSession,
    user: ManagerUser,
    page: Pagination,
    status: SessionStatus | None = None,
    keyword: str | None = None,
) -> Page[SessionPublicOut]:
    return await service.list_sessions(db, status=status, keyword=keyword, page=page, manager=user)


@router.get("/{session_id}", response_model=SessionPublicOut)
async def get_session(session_id: int, db: DbSession, user: OptionalUser) -> SessionPublicOut:
    return await service.get_public_session(db, session_id, user)


@router.post("", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
async def create_session(data: SessionCreateRequest, staff: StaffUser, db: DbSession) -> SessionOut:
    return SessionOut.model_validate(await service.create_session(db, data, staff))


@router.put("/{session_id}", response_model=SessionOut)
async def update_session(session_id: int, data: SessionUpdateRequest, staff: StaffUser, db: DbSession) -> SessionOut:
    return SessionOut.model_validate(await service.update_session(db, session_id, data, staff))


@router.post("/{session_id}/publish", response_model=SessionOut)
async def publish(session_id: int, staff: StaffUser, db: DbSession):
    return await service.publish(db, session_id, staff)


@router.post("/{session_id}/open", response_model=SessionOut)
async def open_session(session_id: int, auctioneer: AuctioneerUser, db: DbSession):
    return await service.open_session(db, session_id, auctioneer)


@router.post("/{session_id}/pause", response_model=SessionOut)
async def pause_session(session_id: int, data: StatusChangeRequest, auctioneer: AuctioneerUser, db: DbSession):
    return await service.pause_session(db, session_id, auctioneer, data.reason)


@router.post("/{session_id}/resume", response_model=SessionOut)
async def resume_session(session_id: int, data: StatusChangeRequest, auctioneer: AuctioneerUser, db: DbSession):
    return await service.resume_session(db, session_id, auctioneer, data.reason)


@router.post("/{session_id}/end", response_model=SessionOut)
async def end_session(session_id: int, data: StatusChangeRequest, auctioneer: AuctioneerUser, db: DbSession):
    return await service.end_session(db, session_id, auctioneer, data.reason)


@router.post("/{session_id}/cancel", response_model=SessionOut)
async def cancel_session(session_id: int, data: StatusChangeRequest, actor: StaffOrAuctioneer, db: DbSession):
    return await service.cancel_session(db, session_id, actor, data.reason)
