"""Kết quả đấu giá theo phiên bản (FR-22, FR-23).

Quy ước đã thống nhất (theo schema auction_results):
- Khi phiên ENDED, hệ thống CHỈ tạo bản 1 ở trạng thái DRAFT, chưa công bố người trúng.
- Đấu giá viên phụ trách xác nhận -> CONFIRMED (mỗi phiên tối đa 1 bản CONFIRMED).
- Điều chỉnh: tạo phiên bản mới (DRAFT) có lý do; khi bản mới được xác nhận thì
  bản CONFIRMED cũ chuyển sang SUPERSEDED.
"""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_activity
from app.core.clock import utcnow
from app.core.exceptions import AppError, BusinessRuleError, ConflictError, NotFoundError
from app.core.money import format_vnd
from app.db.enums import AssetStatus, ResultStatus, SessionStatus, UserRole
from app.db.models import AuctionResult, AuctionSession, Registration, User
from app.modules.bidding import repository as bid_repository
from app.modules.registrations import repository as registration_repository
from app.modules.reports import exporters
from app.modules.results import repository
from app.modules.results.permissions import (
    ensure_can_download_minutes,
    ensure_can_manage_results,
    ensure_can_view_official,
    ensure_can_view_results,
    is_approved_participant,
)
from app.modules.results.schemas import AdjustResultRequest, ConfirmResultRequest, OfficialResultOut, ResultOut
from app.modules.sessions import repository as session_repository


async def create_draft_result(db: AsyncSession, session_id: int) -> AuctionResult | None:
    """Tạo bản kết quả dự thảo đầu tiên. Gọi trong transaction đóng phiên, KHÔNG commit ở đây.

    Trả về None nếu phiên đã có kết quả (tránh tạo trùng khi gọi lại).
    """
    if await repository.latest_version_no(db, session_id) > 0:
        return None

    winning_bid = await bid_repository.get_winning_bid(db, session_id)
    result = AuctionResult(
        session_id=session_id,
        version_no=1,
        winning_bid_id=winning_bid.bid_id if winning_bid else None,
        status=ResultStatus.DRAFT,
        exception_note=None if winning_bid else "Không có lượt trả giá hợp lệ",
    )
    db.add(result)
    await db.flush()
    log_activity(
        db,
        user_id=None,
        action="CREATE_DRAFT_RESULT",
        entity_type="auction_result",
        entity_id=result.result_id,
        new_value=result.winning_bid_id,
    )
    return result


async def _load_session(db: AsyncSession, session_id: int, user: User, *, locked: bool) -> AuctionSession:
    session = (
        await session_repository.get_session_for_update(db, session_id)
        if locked
        else await session_repository.get_session(db, session_id)
    )
    if session is None:
        raise NotFoundError("Không tìm thấy phiên đấu giá")
    if locked:
        ensure_can_manage_results(session, user)
    else:
        ensure_can_view_results(session, user)
    return session


async def _version_outputs(db: AsyncSession, session_id: int) -> list[ResultOut]:
    rows = await repository.list_version_details(db, session_id)
    return [
        ResultOut(
            **{
                field: getattr(result, field)
                for field in ResultOut.model_fields
                if field not in ("winning_amount", "winning_bidder_alias")
            },
            winning_amount=amount,
            winning_bidder_alias=alias,
        )
        for result, amount, alias in rows
    ]


async def list_results(db: AsyncSession, session_id: int, user: User) -> list[ResultOut]:
    await _load_session(db, session_id, user, locked=False)
    return await _version_outputs(db, session_id)


async def confirm_result(
    db: AsyncSession,
    session_id: int,
    result_id: int,
    auctioneer: User,
    data: ConfirmResultRequest,
) -> ResultOut:
    session = await _load_session(db, session_id, auctioneer, locked=True)
    result = await repository.get_result(db, session_id, result_id)
    if result is None:
        raise NotFoundError("Không tìm thấy bản kết quả của phiên này")
    if result.status != ResultStatus.DRAFT:
        raise BusinessRuleError("Chỉ có thể xác nhận bản kết quả dự thảo", code="RESULT_NOT_DRAFT")
    versions = await repository.list_versions(db, session_id)
    for previous in versions:
        if previous.status == ResultStatus.CONFIRMED:
            previous.status = ResultStatus.SUPERSEDED
            log_activity(
                db,
                user_id=auctioneer.user_id,
                action="SUPERSEDE_RESULT",
                entity_type="auction_result",
                entity_id=previous.result_id,
                field_name="status",
                old_value=ResultStatus.CONFIRMED,
                new_value=ResultStatus.SUPERSEDED,
            )
    # Giải phóng unique index của bản CONFIRMED cũ trước khi xác nhận bản mới.
    await db.flush()
    if "exception_note" in data.model_fields_set:
        result.exception_note = data.exception_note
    result.status = ResultStatus.CONFIRMED
    result.confirmed_by = auctioneer.user_id
    result.confirmed_at = utcnow()
    log_activity(
        db,
        user_id=auctioneer.user_id,
        action="CONFIRM_RESULT",
        entity_type="auction_result",
        entity_id=result_id,
        field_name="status",
        old_value=ResultStatus.DRAFT,
        new_value=ResultStatus.CONFIRMED,
    )
    asset = await session_repository.get_asset(db, session.asset_id)
    if asset is None:
        raise NotFoundError("Không tìm thấy tài sản của phiên")
    target_status = AssetStatus.ENDED if result.winning_bid_id is not None else AssetStatus.UPCOMING
    if asset.status != target_status:
        log_activity(
            db,
            user_id=auctioneer.user_id,
            action="UPDATE_ASSET_STATUS",
            entity_type="asset",
            entity_id=asset.asset_id,
            field_name="status",
            old_value=asset.status,
            new_value=target_status,
        )
        asset.status = target_status
    await db.flush()
    output = next(item for item in await _version_outputs(db, session_id) if item.result_id == result_id)
    await db.commit()
    return output


async def adjust_result(
    db: AsyncSession,
    session_id: int,
    auctioneer: User,
    data: AdjustResultRequest,
) -> ResultOut:
    session = await _load_session(db, session_id, auctioneer, locked=True)
    if session.status != SessionStatus.ENDED:
        raise BusinessRuleError("Chỉ có thể điều chỉnh kết quả khi phiên đã kết thúc", code="SESSION_NOT_ENDED")
    versions = await repository.list_versions(db, session_id)
    latest = versions[-1] if versions else None
    if latest is not None and latest.status == ResultStatus.DRAFT:
        raise ConflictError("Còn bản dự thảo chưa được xác nhận", code="DRAFT_RESULT_PENDING")
    if latest is None or latest.status != ResultStatus.CONFIRMED:
        raise ConflictError("Chưa có kết quả đã xác nhận để điều chỉnh", code="NO_CONFIRMED_RESULT")
    if data.winning_bid_id is not None:
        if await repository.get_accepted_bid(db, session_id, data.winning_bid_id) is None:
            raise BusinessRuleError(
                "Lượt giá trúng phải được chấp nhận và thuộc đúng phiên", code="INVALID_WINNING_BID"
            )
    result = AuctionResult(
        session_id=session_id,
        version_no=latest.version_no + 1,
        status=ResultStatus.DRAFT,
        winning_bid_id=data.winning_bid_id,
        exception_note=data.exception_note,
        adjustment_reason=data.adjustment_reason,
        confirmed_by=None,
        confirmed_at=None,
        minutes_url=None,
    )
    db.add(result)
    await db.flush()
    log_activity(
        db,
        user_id=auctioneer.user_id,
        action="ADJUST_RESULT",
        entity_type="auction_result",
        entity_id=result.result_id,
        field_name="winning_bid_id",
        old_value=latest.winning_bid_id,
        new_value=result.winning_bid_id,
        reason=data.adjustment_reason,
    )
    output = next(item for item in await _version_outputs(db, session_id) if item.result_id == result.result_id)
    await db.commit()
    return output


STATUS_LABELS = {
    ResultStatus.DRAFT: "DỰ THẢO",
    ResultStatus.CONFIRMED: "ĐÃ XÁC NHẬN",
    ResultStatus.SUPERSEDED: "ĐÃ BỊ THAY THẾ",
}


def _fmt_time(value: datetime | None) -> str | None:
    return value.strftime("%d/%m/%Y %H:%M:%S") + " (UTC)" if value else None


async def _participant_registration(db: AsyncSession, session_id: int, user: User) -> Registration | None:
    if user.role != UserRole.BIDDER:
        return None
    return await registration_repository.get_registration_for_bidder(db, session_id, user.user_id)


async def render_minutes(db: AsyncSession, session_id: int, result_id: int, user: User) -> tuple[bytes, int]:
    """Sinh biên bản PDF của một phiên bản kết quả (FR-23). Trả (nội dung PDF, version_no)."""
    session = await session_repository.get_session(db, session_id)
    if session is None:
        raise NotFoundError("Không tìm thấy phiên đấu giá")
    detail = await repository.get_version_detail(db, session_id, result_id)
    if detail is None:
        raise NotFoundError("Không tìm thấy bản kết quả của phiên này")
    result, winning_amount, winner_alias = detail
    registration = await _participant_registration(db, session_id, user)
    ensure_can_download_minutes(session, user, registration, result)

    asset = await session_repository.get_asset(db, session.asset_id)
    confirmer = await session_repository.get_user(db, result.confirmed_by) if result.confirmed_by else None
    bids = await repository.list_accepted_bids(db, session_id)
    context = {
        "session_code": f"PDG-{session.session_id}",
        "asset_code": asset.asset_code if asset else "",
        "asset_name": asset.name if asset else "",
        "version_no": result.version_no,
        "status_label": STATUS_LABELS.get(result.status, result.status),
        "starting_price": format_vnd(session.starting_price),
        "bid_increment": format_vnd(session.bid_increment),
        "winner_alias": winner_alias if result.winning_bid_id else None,
        "winning_amount": format_vnd(winning_amount) if winning_amount is not None else None,
        "exception_note": result.exception_note,
        "adjustment_reason": result.adjustment_reason,
        "confirmed_by_name": confirmer.full_name if confirmer else None,
        "confirmed_at": _fmt_time(result.confirmed_at),
        "bids": [
            {
                "sequence_no": bid.sequence_no,
                "bidder_alias": alias,
                "amount": format_vnd(bid.amount),
                "server_time": _fmt_time(bid.server_time),
            }
            for bid, alias in bids
        ],
        "generated_at": _fmt_time(utcnow()),
    }
    try:
        content = exporters.render_pdf("minutes.html", context)
    except (OSError, ImportError) as exc:
        raise AppError(
            "Không thể xuất PDF vì thiếu thư viện hệ thống. Vui lòng chạy bằng Docker.",
            code="PDF_ENGINE_UNAVAILABLE",
            status_code=503,
        ) from exc
    log_activity(
        db,
        user_id=user.user_id,
        action="EXPORT_MINUTES",
        entity_type="auction_result",
        entity_id=result.result_id,
        new_value=str(result.version_no),
    )
    await db.commit()
    return content, result.version_no


async def get_official_result(db: AsyncSession, session_id: int, user: User) -> OfficialResultOut:
    """FR-23: chỉ trả bản CONFIRMED; người tham gia phải có hồ sơ APPROVED trong phiên. Chỉ đọc."""
    session = await session_repository.get_session(db, session_id)
    if session is None:
        raise NotFoundError("Không tìm thấy phiên đấu giá")
    registration = await _participant_registration(db, session_id, user)
    ensure_can_view_official(session, user, registration)
    detail = await repository.get_confirmed_detail(db, session_id)
    if detail is None:
        raise NotFoundError("Phiên chưa có kết quả đã xác nhận", code="NO_CONFIRMED_RESULT")
    result, amount, alias, winner_registration_id = detail
    mine = is_approved_participant(user, registration)
    return OfficialResultOut(
        result_id=result.result_id,
        session_id=session.session_id,
        session_code=f"PDG-{session.session_id}",
        version_no=result.version_no,
        confirmed_at=result.confirmed_at,
        is_failed=result.winning_bid_id is None,
        winning_bidder_alias=alias if result.winning_bid_id else None,
        winning_amount=amount if result.winning_bid_id else None,
        exception_note=result.exception_note,
        my_alias=registration.bidder_alias if mine and registration else None,
        is_mine=bool(
            mine
            and registration
            and winner_registration_id is not None
            and winner_registration_id == registration.registration_id
        ),
    )
