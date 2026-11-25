"""Nhận lệnh trả giá và cung cấp trạng thái phòng (FR-18 - FR-21, NFR-03, NFR-06).

Luồng nhận giá (một transaction):
  1. Khóa dòng phiên bằng SELECT ... FOR UPDATE => các lệnh cùng phiên xếp hàng tuần tự.
  2. Nếu transaction_code đã có: trả lại kết quả cũ (chống gửi trùng).
  3. Kiểm tra trạng thái/thời hạn phiên, quyền người gửi, mức giá (rules.py).
  4. Ghi bid ACCEPTED hoặc REJECTED (kèm lý do) với sequence_no tiếp theo, rồi COMMIT.
  5. SAU KHI COMMIT mới phát sự kiện vào phòng.
"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import utcnow
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.realtime import EVENT_BID_ACCEPTED, manager
from app.db.enums import BidResult, RegistrationStatus, SessionStatus, UserRole
from app.db.models import AuctionSession, Bid, User
from app.modules.bidding import repository
from app.modules.bidding.rules import check_bid_amount, minimum_next_bid
from app.modules.bidding.schemas import BidOut, PlaceBidRequest, PublicBidOut, SessionStateOut
from app.modules.sessions import repository as session_repository
from app.modules.sessions.permissions import can_view_internal

RECENT_BIDS_LIMIT = 20


@dataclass
class _Outcome:
    bid: Bid
    duplicated: bool


def _to_out(outcome: _Outcome) -> BidOut:
    b = outcome.bid
    return BidOut(
        bid_id=b.bid_id,
        transaction_code=b.transaction_code,
        amount=b.amount,
        result=b.result,
        rejection_reason=b.rejection_reason,
        sequence_no=b.sequence_no,
        server_time=b.server_time,
        duplicated=outcome.duplicated,
    )


async def place_bid(db: AsyncSession, session_id: int, bidder: User, data: PlaceBidRequest) -> BidOut:
    session = await session_repository.get_session_for_update(db, session_id)
    if session is None:
        raise NotFoundError("Không tìm thấy phiên đấu giá")

    registration = await repository.get_registration(db, session_id, bidder.user_id)
    if registration is None or registration.status != RegistrationStatus.APPROVED:
        # Không có hồ sơ đã duyệt thì không có registration_id để ghi bid -> từ chối ở API
        raise ForbiddenError("Bạn không có trong danh sách đủ điều kiện của phiên này")

    existing = await repository.get_bid_by_transaction_code(db, data.transaction_code)
    if existing is not None:
        if existing.registration_id != registration.registration_id:
            raise ConflictError("Mã giao dịch đã được sử dụng", code="DUPLICATE_TRANSACTION")
        out = _to_out(_Outcome(existing, duplicated=True))
        await db.rollback()  # nhả khóa phiên, không ghi gì thêm
        return out

    now = utcnow()
    reason: str | None = None
    if session.status != SessionStatus.IN_PROGRESS:
        reason = "Phiên không ở trạng thái đang diễn ra"
    elif now >= session.end_time:
        reason = "Phiên đã hết thời gian nhận giá"

    highest = await repository.get_highest_accepted(db, session_id)
    if reason is None:
        check = check_bid_amount(
            data.amount,
            starting_price=session.starting_price,
            bid_increment=session.bid_increment,
            highest_accepted=highest,
        )
        reason = check.reason

    bid = Bid(
        transaction_code=data.transaction_code,
        registration_id=registration.registration_id,
        amount=data.amount,
        result=BidResult.ACCEPTED if reason is None else BidResult.REJECTED,
        rejection_reason=reason,
        sequence_no=await repository.next_sequence_no(db, session_id),
        server_time=now,
    )
    db.add(bid)
    await db.commit()

    if bid.result == BidResult.ACCEPTED:
        await manager.broadcast(
            session_id,
            EVENT_BID_ACCEPTED,
            {
                "sequence_no": bid.sequence_no,
                "bidder_alias": registration.bidder_alias,
                "amount": bid.amount,
                "highest_accepted": bid.amount,
                "minimum_next_bid": bid.amount + session.bid_increment,
                "server_time": bid.server_time,
            },
        )
    return _to_out(_Outcome(bid, duplicated=False))


async def _ensure_can_view_room(db: AsyncSession, session: AuctionSession, user: User) -> str | None:
    """Trả về bidder_alias nếu là người tham gia đủ điều kiện; None nếu là người nội bộ."""
    if can_view_internal(session, user):
        return None
    if user.role == UserRole.BIDDER:
        registration = await repository.get_registration(db, session.session_id, user.user_id)
        if registration is not None and registration.status == RegistrationStatus.APPROVED:
            return registration.bidder_alias
    raise ForbiddenError("Bạn không có quyền vào phòng đấu giá này")


async def get_room_state(db: AsyncSession, session_id: int, user: User) -> SessionStateOut:
    session = await session_repository.get_session(db, session_id)
    if session is None:
        raise NotFoundError("Không tìm thấy phiên đấu giá")
    my_alias = await _ensure_can_view_room(db, session, user)

    highest = await repository.get_highest_accepted(db, session_id)
    rows = await repository.list_bids(db, session_id, include_rejected=False, limit=RECENT_BIDS_LIMIT)
    return SessionStateOut(
        session_id=session.session_id,
        code=session.code,
        status=session.status,
        starting_price=session.starting_price,
        bid_increment=session.bid_increment,
        highest_accepted=highest,
        minimum_next_bid=minimum_next_bid(
            starting_price=session.starting_price,
            bid_increment=session.bid_increment,
            highest_accepted=highest,
        ),
        start_time=session.start_time,
        end_time=session.end_time,
        server_time=utcnow(),
        my_alias=my_alias,
        recent_bids=[
            PublicBidOut(
                sequence_no=b.sequence_no,
                bidder_alias=alias,
                amount=b.amount,
                result=b.result,
                server_time=b.server_time,
            )
            for b, alias in rows
        ],
    )


async def list_bid_history(
    db: AsyncSession,
    session_id: int,
    user: User,
    *,
    include_rejected: bool,
    limit: int,
    offset: int,
) -> list[PublicBidOut]:
    """FR-21: người tham gia xem lượt đã chấp nhận (mã ẩn danh); nội bộ xem được cả lệnh bị từ chối."""
    session = await session_repository.get_session(db, session_id)
    if session is None:
        raise NotFoundError("Không tìm thấy phiên đấu giá")
    my_alias = await _ensure_can_view_room(db, session, user)
    internal = my_alias is None
    rows = await repository.list_bids(
        db,
        session_id,
        include_rejected=include_rejected and internal,
        limit=limit,
        offset=offset,
    )
    return [
        PublicBidOut(
            sequence_no=b.sequence_no,
            bidder_alias=alias,
            amount=b.amount,
            result=b.result,
            rejection_reason=b.rejection_reason if internal else None,
            server_time=b.server_time,
        )
        for b, alias in rows
    ]
