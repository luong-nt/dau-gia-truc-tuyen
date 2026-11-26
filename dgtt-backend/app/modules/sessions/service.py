"""Điều hành trạng thái phiên đấu giá (FR-17) và công khai phiên (FR-08).

Mỗi thao tác: khóa dòng phiên -> kiểm tra máy trạng thái + quyền -> đổi trạng thái
-> cập nhật tài sản liên quan -> ghi nhật ký -> COMMIT -> phát sự kiện realtime.
"""

from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_activity
from app.core.clock import utcnow
from app.core.exceptions import BusinessRuleError, ConflictError, ForbiddenError, NotFoundError
from app.core.pagination import Page, PageParams
from app.core.realtime import EVENT_STATUS_CHANGED, manager
from app.db.enums import AssetStatus, SessionStatus, UserRole, UserStatus
from app.db.models import Asset, AuctionSession, User
from app.modules.sessions import repository
from app.modules.sessions.permissions import ensure_assigned_auctioneer
from app.modules.sessions.schemas import SessionCreateRequest, SessionOut, SessionPublicOut, SessionUpdateRequest
from app.modules.sessions.state_machine import ensure_transition


async def _load_for_update(db: AsyncSession, session_id: int) -> AuctionSession:
    session = await repository.get_session_for_update(db, session_id)
    if session is None:
        raise NotFoundError("Không tìm thấy phiên đấu giá")
    return session


async def _apply(
    db: AsyncSession,
    session: AuctionSession,
    target: SessionStatus,
    actor: User,
    *,
    action: str,
    reason: str | None,
    early_end: bool = False,
    logged_at: datetime | None = None,
) -> AuctionSession:
    old_status = session.status
    ensure_transition(old_status, target, reason=reason, early_end=early_end)
    session.status = target
    await _sync_asset_status(db, session, target)
    log_activity(
        db,
        user_id=actor.user_id,
        action=action,
        entity_type="auction_session",
        entity_id=session.session_id,
        field_name="status",
        old_value=old_status,
        new_value=target,
        reason=reason,
        created_at=logged_at,
    )
    if target == SessionStatus.ENDED:
        # Tạo kết quả dự thảo trong cùng transaction (FR-22)
        from app.modules.results.service import create_draft_result

        await create_draft_result(db, session.session_id)
    await db.commit()
    await manager.broadcast(
        session.session_id,
        EVENT_STATUS_CHANGED,
        {
            "session_id": session.session_id,
            "old_status": old_status,
            "status": target,
            "end_time": session.end_time,
            "reason": reason,
        },
    )
    return session


async def _sync_asset_status(db: AsyncSession, session: AuctionSession, target: SessionStatus) -> None:
    """Đồng bộ trạng thái tài sản theo phiên (quy ước đã thống nhất)."""
    asset = await repository.get_asset(db, session.asset_id)
    if asset is None:
        return
    if target == SessionStatus.OPEN_FOR_REGISTRATION:
        asset.is_public = True
    elif target == SessionStatus.IN_PROGRESS:
        asset.status = AssetStatus.IN_AUCTION
    elif target == SessionStatus.CANCELLED and asset.status == AssetStatus.IN_AUCTION:
        asset.status = AssetStatus.UPCOMING  # để có thể tổ chức lại
    # ENDED: tài sản giữ IN_AUCTION cho đến khi kết quả được xác nhận (module results)


async def publish(db: AsyncSession, session_id: int, staff: User) -> AuctionSession:
    """DRAFT -> OPEN_FOR_REGISTRATION. Thời điểm công khai được lưu trong activity_logs."""
    session = await _load_for_update(db, session_id)
    if utcnow() >= session.registration_deadline:
        raise BusinessRuleError("Đã qua hạn nhận hồ sơ, không thể công khai phiên")
    return await _apply(db, session, SessionStatus.OPEN_FOR_REGISTRATION, staff, action="PUBLISH_SESSION", reason=None)


async def open_session(db: AsyncSession, session_id: int, auctioneer: User) -> AuctionSession:
    """UPCOMING -> IN_PROGRESS, chỉ khi đã đến giờ bắt đầu và chưa quá giờ kết thúc."""
    session = await _load_for_update(db, session_id)
    ensure_assigned_auctioneer(session, auctioneer)
    now = utcnow()
    if now < session.start_time:
        raise BusinessRuleError("Chưa đến giờ bắt đầu phiên")
    if now >= session.end_time:
        raise BusinessRuleError("Đã quá giờ kết thúc phiên")
    return await _apply(db, session, SessionStatus.IN_PROGRESS, auctioneer, action="OPEN_SESSION", reason=None)


async def pause_session(db: AsyncSession, session_id: int, auctioneer: User, reason: str | None) -> AuctionSession:
    session = await _load_for_update(db, session_id)
    ensure_assigned_auctioneer(session, auctioneer)
    # TASK-012: mốc tạm dừng là thời điểm thực tế SAU khi lấy được khoá phiên (không phải lúc bắt đầu transaction),
    # để resume không cộng bù cả thời gian chờ khoá khi phiên vẫn còn IN_PROGRESS.
    return await _apply(
        db, session, SessionStatus.PAUSED, auctioneer, action="PAUSE_SESSION", reason=reason, logged_at=utcnow()
    )


async def resume_session(db: AsyncSession, session_id: int, auctioneer: User, reason: str | None) -> AuctionSession:
    """PAUSED -> IN_PROGRESS. Quy chế (người dùng chọn A, TASK-012): cộng bù đúng thời gian đã tạm dừng vào end_time.

    Sự kiện status_changed phát sau commit mang end_time mới để đồng hồ các bên cập nhật (FR-19).
    """
    session = await _load_for_update(db, session_id)
    ensure_assigned_auctioneer(session, auctioneer)
    # UPCOMING -> IN_PROGRESS là thao tác MỞ phiên (kiểm giờ bắt đầu), không được đi qua RESUME.
    if session.status != SessionStatus.PAUSED:
        raise BusinessRuleError(
            f"Chỉ tiếp tục được phiên đang tạm dừng (hiện tại: {session.status})", code="INVALID_STATUS_TRANSITION"
        )
    ensure_transition(session.status, SessionStatus.IN_PROGRESS, reason=reason)
    now = utcnow()
    paused_at = await repository.get_last_pause_time(db, session_id)
    pause_duration = max(now - paused_at, timedelta(0)) if paused_at else timedelta(0)
    old_end = session.end_time
    new_end = old_end + pause_duration
    if now >= new_end:
        raise BusinessRuleError("Đã quá giờ kết thúc phiên, không thể tiếp tục")
    if pause_duration > timedelta(0):
        session.end_time = new_end
        log_activity(
            db,
            user_id=auctioneer.user_id,
            action="EXTEND_END_TIME",
            entity_type="auction_session",
            entity_id=session.session_id,
            field_name="end_time",
            old_value=old_end.isoformat(),
            new_value=new_end.isoformat(),
            reason=f"Bù thời gian tạm dừng {round(pause_duration.total_seconds())} giây",
        )
    return await _apply(db, session, SessionStatus.IN_PROGRESS, auctioneer, action="RESUME_SESSION", reason=reason)


async def end_session(db: AsyncSession, session_id: int, auctioneer: User, reason: str | None) -> AuctionSession:
    """Đóng phiên chủ động. Đóng trước end_time bắt buộc có lý do."""
    session = await _load_for_update(db, session_id)
    ensure_assigned_auctioneer(session, auctioneer)
    early = utcnow() < session.end_time
    return await _apply(
        db, session, SessionStatus.ENDED, auctioneer, action="END_SESSION", reason=reason, early_end=early
    )


async def cancel_session(db: AsyncSession, session_id: int, actor: User, reason: str | None) -> AuctionSession:
    """Nhân viên hủy phiên chưa diễn ra; khi đang diễn ra chỉ đấu giá viên phụ trách được hủy."""
    session = await _load_for_update(db, session_id)
    running = session.status in (SessionStatus.IN_PROGRESS, SessionStatus.PAUSED)
    if running:
        ensure_assigned_auctioneer(session, actor)
    elif actor.role != UserRole.STAFF:
        raise ForbiddenError("Chỉ nhân viên được hủy phiên chưa diễn ra")
    return await _apply(db, session, SessionStatus.CANCELLED, actor, action="CANCEL_SESSION", reason=reason)


def _validate_schedule(data: SessionCreateRequest | SessionOut, *, check_start: bool) -> None:
    if (
        data.registration_deadline >= data.start_time
        or data.deposit_deadline >= data.start_time
        or data.start_time >= data.end_time
        or (check_start and data.start_time <= utcnow())
    ):
        raise BusinessRuleError("Các mốc thời gian của phiên không hợp lệ", code="INVALID_SCHEDULE")


async def _validate_auctioneer(db: AsyncSession, user_id: int) -> None:
    user = await repository.get_user(db, user_id)
    if user is None or user.role != UserRole.AUCTIONEER or user.status != UserStatus.ACTIVE:
        raise BusinessRuleError("Đấu giá viên không hợp lệ hoặc đã bị khóa", code="INVALID_AUCTIONEER")


async def create_session(db: AsyncSession, data: SessionCreateRequest, staff: User) -> AuctionSession:
    asset = await repository.get_asset_for_update(db, data.asset_id)
    if asset is None:
        raise NotFoundError("Không tìm thấy tài sản")
    if asset.status in (AssetStatus.ENDED, AssetStatus.SUSPENDED_CANCELLED):
        raise BusinessRuleError("Tài sản không sẵn sàng đấu giá", code="ASSET_NOT_AVAILABLE")
    if await repository.has_active_session(db, data.asset_id):
        raise ConflictError("Tài sản đã có phiên chưa kết thúc", code="ASSET_HAS_ACTIVE_SESSION")
    await _validate_auctioneer(db, data.auctioneer_id)
    _validate_schedule(data, check_start=True)
    session = AuctionSession(**data.model_dump(exclude={"reason"}), status=SessionStatus.DRAFT)
    db.add(session)
    await db.flush()
    log_activity(
        db, user_id=staff.user_id, action="CREATE_SESSION", entity_type="auction_session", entity_id=session.session_id
    )
    await db.commit()
    return session


async def update_session(
    db: AsyncSession,
    session_id: int,
    data: SessionUpdateRequest,
    staff: User,
) -> AuctionSession:
    session = await _load_for_update(db, session_id)
    if session.status not in (SessionStatus.DRAFT, SessionStatus.OPEN_FOR_REGISTRATION, SessionStatus.UPCOMING):
        raise BusinessRuleError("Không thể sửa cấu hình phiên ở trạng thái hiện tại", code="SESSION_LOCKED")
    if session.status != SessionStatus.DRAFT and not (data.reason and data.reason.strip()):
        raise BusinessRuleError("Cần nhập lý do thay đổi phiên đã công khai", code="REASON_REQUIRED")
    updates = data.model_dump(exclude_unset=True, exclude={"reason"})
    if "auctioneer_id" in updates:
        await _validate_auctioneer(db, data.auctioneer_id)
    merged = SessionOut.model_validate(session).model_copy(update=updates)
    _validate_schedule(merged, check_start="start_time" in updates and merged.start_time != session.start_time)
    for field, value in updates.items():
        old_value = getattr(session, field)
        if old_value == value:
            continue
        log_activity(
            db,
            user_id=staff.user_id,
            action="UPDATE_SESSION",
            entity_type="auction_session",
            entity_id=session_id,
            field_name=field,
            old_value=old_value,
            new_value=value,
            reason=data.reason,
        )
        setattr(session, field, value)
    await db.commit()
    return session


def _public_output(session: AuctionSession, asset: Asset) -> SessionPublicOut:
    return SessionPublicOut(
        **SessionOut.model_validate(session).model_dump(), asset_code=asset.asset_code, asset_name=asset.name
    )


async def list_sessions(
    db: AsyncSession,
    *,
    status: SessionStatus | None,
    keyword: str | None,
    page: PageParams,
    manager: User | None = None,
) -> Page[SessionPublicOut]:
    rows, total = await repository.list_sessions(
        db, status=status, keyword=keyword, offset=page.offset, limit=page.size, manager=manager
    )
    return Page[SessionPublicOut](
        items=[_public_output(session, asset) for session, asset in rows], total=total, page=page.page, size=page.size
    )


async def get_public_session(db: AsyncSession, session_id: int, user: User | None) -> SessionPublicOut:
    session = await repository.get_session(db, session_id)
    if session is None:
        raise NotFoundError("Không tìm thấy phiên đấu giá")
    can_view_draft = user is not None and (
        user.role in (UserRole.STAFF, UserRole.ADMIN)
        or (user.role == UserRole.AUCTIONEER and user.user_id == session.auctioneer_id)
    )
    if session.status == SessionStatus.DRAFT and not can_view_draft:
        raise NotFoundError("Không tìm thấy phiên đấu giá")
    asset = await repository.get_asset(db, session.asset_id)
    if asset is None:
        raise NotFoundError("Không tìm thấy tài sản")
    return _public_output(session, asset)
