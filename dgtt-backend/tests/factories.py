"""Hàm tạo dữ liệu riêng cho test (không sửa `seeds/`).

`seed()` trong `seeds/seed_dev.py` chỉ tạo phiên IN_PROGRESS. Các hàm ở đây tạo thêm phiên ở trạng thái bất kỳ
(ví dụ OPEN_FOR_REGISTRATION), người tham gia chưa có hồ sơ, hồ sơ và lịch sử xét duyệt để test các luồng hồ sơ.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import utcnow
from app.core.security import hash_password
from app.db.enums import (
    AssetStatus,
    BidResult,
    OwnerType,
    RegistrationStatus,
    ResultStatus,
    SessionStatus,
    UserRole,
    UserStatus,
)
from app.db.models import (
    Asset,
    AssetOwner,
    AuctionResult,
    AuctionSession,
    Bid,
    Registration,
    RegistrationReview,
    User,
)
from seeds.seed_dev import DEFAULT_PASSWORD, seed


async def login_headers(client: AsyncClient, username: str) -> dict[str, str]:
    response = await client.post("/api/v1/auth/login", json={"login": username, "password": DEFAULT_PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def create_user(db: AsyncSession, *, username: str, role: UserRole = UserRole.BIDDER) -> User:
    user = User(
        role=role,
        username=username,
        email=f"{username}@dgtt.local",
        full_name=f"Người dùng {username}",
        password_hash=hash_password(DEFAULT_PASSWORD),
        status=UserStatus.ACTIVE,
    )
    db.add(user)
    await db.commit()
    return user


async def create_asset(
    db: AsyncSession,
    *,
    created_by: int,
    asset_code: str | None = None,
    name: str = "Tài sản test hồ sơ",
    status: AssetStatus = AssetStatus.UPCOMING,
) -> Asset:
    """Tạo người có tài sản + tài sản (chưa có phiên). `asset_code` tối đa 30 ký tự."""
    tag = uuid.uuid4().hex[:12]
    owner = AssetOwner(owner_type=OwnerType.INDIVIDUAL, name="Chủ tài sản test", id_number=f"OW{tag}")
    db.add(owner)
    await db.flush()
    asset = Asset(
        asset_code=asset_code or f"TSR-{tag}",
        owner_id=owner.owner_id,
        name=name,
        status=status,
        is_public=True,
        created_by=created_by,
    )
    db.add(asset)
    await db.commit()
    return asset


async def create_session(
    db: AsyncSession,
    *,
    auctioneer_id: int,
    created_by: int,
    status: SessionStatus = SessionStatus.OPEN_FOR_REGISTRATION,
    registration_deadline: datetime | None = None,
    asset_id: int | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> AuctionSession:
    """Tạo phiên ở trạng thái `status` (kèm người có tài sản + tài sản mới nếu không truyền `asset_id`).

    Mặc định hạn nộp hồ sơ là 2 ngày nữa. Truyền `registration_deadline` trong quá khứ để giả lập phiên đã quá hạn.
    Truyền `start_time` để kiểm soát thứ tự sắp xếp (phải sau hạn nộp hồ sơ).
    """
    now = utcnow()
    deadline = registration_deadline or now + timedelta(days=2)
    start_time = start_time or max(deadline, now) + timedelta(days=1)

    if asset_id is None:
        asset_id = (await create_asset(db, created_by=created_by)).asset_id
    session = AuctionSession(
        asset_id=asset_id,
        auctioneer_id=auctioneer_id,
        starting_price=Decimal("100000000"),
        bid_increment=Decimal("5000000"),
        deposit_amount=Decimal("20000000"),
        registration_deadline=deadline,
        deposit_deadline=deadline,
        start_time=start_time,
        end_time=end_time or start_time + timedelta(hours=1),
        status=status,
        notice_content="Thông báo đấu giá test",
    )
    db.add(session)
    await db.commit()
    return session


async def create_registration(
    db: AsyncSession,
    *,
    session_id: int,
    bidder: User,
    status: RegistrationStatus = RegistrationStatus.PENDING,
    submitted_at: datetime | None = None,
    supplement_deadline: datetime | None = None,
    bidder_alias: str | None = None,
) -> Registration:
    registration = Registration(
        session_id=session_id,
        bidder_id=bidder.user_id,
        submitted_full_name=bidder.full_name,
        submitted_id_number=f"{bidder.user_id:012d}",
        status=status,
        supplement_deadline=supplement_deadline,
        bidder_alias=bidder_alias,
        submitted_at=submitted_at or utcnow(),
    )
    db.add(registration)
    await db.commit()
    return registration


async def add_review(
    db: AsyncSession,
    *,
    registration_id: int,
    review_type: str,
    reviewed_by: int,
    result: str | None = None,
    reason: str | None = None,
    evidence: str | None = None,
    reviewed_at: datetime | None = None,
) -> RegistrationReview:
    review = RegistrationReview(
        registration_id=registration_id,
        review_type=review_type,
        result=result,
        reason=reason,
        evidence=evidence,
        reviewed_by=reviewed_by,
        reviewed_at=reviewed_at or utcnow(),
    )
    db.add(review)
    await db.commit()
    return review


@dataclass
class RegistrationScenario:
    """users: admin, staff, auctioneer, bidder1..n (người tham gia CHƯA có hồ sơ trong `session`)."""

    users: dict[str, User]
    session: AuctionSession


async def create_registration_scenario(
    db: AsyncSession,
    *,
    prefix: str,
    status: SessionStatus = SessionStatus.OPEN_FOR_REGISTRATION,
    registration_deadline: datetime | None = None,
    bidder_count: int = 3,
) -> RegistrationScenario:
    """Dùng `seed()` để có admin/staff/auctioneer, rồi tạo người tham gia mới và một phiên ở trạng thái `status`."""
    data = await seed(db, prefix=prefix, bidder_count=0)
    users = dict(data.users)
    for i in range(1, bidder_count + 1):
        users[f"bidder{i}"] = await create_user(db, username=f"{prefix}rbidder{i}")
    session = await create_session(
        db,
        auctioneer_id=users["auctioneer"].user_id,
        created_by=users["staff"].user_id,
        status=status,
        registration_deadline=registration_deadline,
    )
    return RegistrationScenario(users=users, session=session)


async def create_bid(
    db: AsyncSession,
    *,
    registration_id: int,
    amount: int | Decimal,
    sequence_no: int,
    result: BidResult = BidResult.ACCEPTED,
    rejection_reason: str | None = None,
) -> Bid:
    bid = Bid(
        transaction_code=f"TX-{uuid.uuid4().hex}",
        registration_id=registration_id,
        amount=Decimal(amount),
        result=result,
        rejection_reason=rejection_reason if result == BidResult.ACCEPTED else rejection_reason or "Giá không hợp lệ",
        sequence_no=sequence_no,
    )
    db.add(bid)
    await db.commit()
    return bid


async def create_result(
    db: AsyncSession,
    *,
    session_id: int,
    version_no: int = 1,
    winning_bid_id: int | None = None,
    status: ResultStatus = ResultStatus.DRAFT,
    exception_note: str | None = None,
    adjustment_reason: str | None = None,
    confirmed_by: int | None = None,
) -> AuctionResult:
    result = AuctionResult(
        session_id=session_id,
        version_no=version_no,
        winning_bid_id=winning_bid_id,
        status=status,
        exception_note=exception_note,
        adjustment_reason=adjustment_reason,
        confirmed_by=confirmed_by,
        confirmed_at=utcnow() if status != ResultStatus.DRAFT else None,
    )
    db.add(result)
    await db.commit()
    return result


@dataclass
class ResultScenario:
    """Phiên ENDED, tài sản IN_AUCTION, 2 hồ sơ APPROVED (NTG-01 = bidder1, NTG-02 = bidder2).

    Lượt giá: NTG-01 100tr (ACCEPTED, #1), NTG-02 105tr (ACCEPTED, #2), NTG-01 103tr (REJECTED, #3).
    `draft`: bản 1 DRAFT, người trúng = lượt 105tr của NTG-02 (trừ khi `with_winner=False`).
    """

    users: dict[str, User]
    session: AuctionSession
    asset: Asset
    registrations: dict[str, Registration]
    bids: dict[str, Bid]
    draft: AuctionResult | None


async def create_result_scenario(
    db: AsyncSession,
    *,
    prefix: str,
    session_status: SessionStatus = SessionStatus.ENDED,
    with_winner: bool = True,
    with_draft: bool = True,
) -> ResultScenario:
    data = await seed(db, prefix=prefix, bidder_count=0)
    users = dict(data.users)
    users["auctioneer2"] = await create_user(db, username=f"{prefix}auctioneer2", role=UserRole.AUCTIONEER)
    for i in (1, 2):
        users[f"bidder{i}"] = await create_user(db, username=f"{prefix}xbidder{i}")
    users["outsider"] = await create_user(db, username=f"{prefix}outsider")

    now = utcnow()
    asset = await create_asset(db, created_by=users["staff"].user_id, status=AssetStatus.IN_AUCTION)
    session = await create_session(
        db,
        auctioneer_id=users["auctioneer"].user_id,
        created_by=users["staff"].user_id,
        status=session_status,
        registration_deadline=now - timedelta(days=2),
        asset_id=asset.asset_id,
        start_time=now - timedelta(hours=2),
        end_time=now - timedelta(minutes=5),
    )
    registrations = {
        f"NTG-0{i}": await create_registration(
            db,
            session_id=session.session_id,
            bidder=users[f"bidder{i}"],
            status=RegistrationStatus.APPROVED,
            bidder_alias=f"NTG-0{i}",
        )
        for i in (1, 2)
    }
    bids: dict[str, Bid] = {}
    if with_winner:
        bids["first"] = await create_bid(
            db, registration_id=registrations["NTG-01"].registration_id, amount=100_000_000, sequence_no=1
        )
        bids["winner"] = await create_bid(
            db, registration_id=registrations["NTG-02"].registration_id, amount=105_000_000, sequence_no=2
        )
        bids["rejected"] = await create_bid(
            db,
            registration_id=registrations["NTG-01"].registration_id,
            amount=103_000_000,
            sequence_no=3,
            result=BidResult.REJECTED,
            rejection_reason="Giá phải lớn hơn giá cao nhất hiện tại",
        )
    draft = None
    if with_draft:
        draft = await create_result(
            db,
            session_id=session.session_id,
            winning_bid_id=bids["winner"].bid_id if with_winner else None,
            exception_note=None if with_winner else "Không có lượt trả giá hợp lệ",
        )
    return ResultScenario(
        users=users, session=session, asset=asset, registrations=registrations, bids=bids, draft=draft
    )
