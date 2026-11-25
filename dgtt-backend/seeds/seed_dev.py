"""Tạo dữ liệu mẫu cho môi trường dev/test (NFR-09).

Chạy:  python -m seeds.seed_dev
Mật khẩu chung của mọi tài khoản mẫu: Matkhau@123

Tạo ra:
- 5 tài khoản: admin, staff, auctioneer, bidder1, bidder2
- 1 người có tài sản, 1 tài sản
- 1 phiên ĐANG DIỄN RA (IN_PROGRESS) kết thúc sau 60 phút, giá khởi điểm 100.000.000 đ,
  bước giá 5.000.000 đ; bidder1 (NTG-01) và bidder2 (NTG-02) đã được duyệt.
"""

import asyncio
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import utcnow
from app.core.security import hash_password
from app.db.enums import (
    AssetStatus,
    OwnerType,
    RegistrationStatus,
    SessionStatus,
    UserRole,
    UserStatus,
)
from app.db.models import Asset, AssetOwner, AuctionSession, Registration, User
from app.db.session import SessionLocal, engine

DEFAULT_PASSWORD = "Matkhau@123"


@dataclass
class SeedData:
    users: dict[str, User]
    session: AuctionSession
    registrations: list[Registration]


async def seed(db: AsyncSession, *, prefix: str = "", minutes_left: int = 60, bidder_count: int = 2) -> SeedData:
    """`prefix` giúp test tạo nhiều bộ dữ liệu không trùng tên trong cùng một DB."""
    password_hash = hash_password(DEFAULT_PASSWORD)

    def make_user(username: str, role: UserRole, full_name: str) -> User:
        return User(
            role=role,
            username=f"{prefix}{username}",
            email=f"{prefix}{username}@dgtt.local",
            full_name=full_name,
            password_hash=password_hash,
            status=UserStatus.ACTIVE,
        )

    users = {
        "admin": make_user("admin", UserRole.ADMIN, "Quản trị viên"),
        "staff": make_user("staff", UserRole.STAFF, "Nhân viên Một"),
        "auctioneer": make_user("auctioneer", UserRole.AUCTIONEER, "Đấu giá viên Một"),
    }
    for i in range(1, bidder_count + 1):
        users[f"bidder{i}"] = make_user(f"bidder{i}", UserRole.BIDDER, f"Người tham gia {i}")
    db.add_all(users.values())
    await db.flush()

    owner = AssetOwner(
        owner_type=OwnerType.ORGANIZATION,
        name="Công ty TNHH Mẫu",
        id_number=f"{prefix}0101234567"[-20:],
        representative_name="Nguyễn Văn A",
    )
    db.add(owner)
    await db.flush()

    asset = Asset(
        asset_code=f"{prefix}TS-0001"[-30:],
        owner_id=owner.owner_id,
        name="Xe ô tô Toyota Vios 2020",
        description="Tài sản mẫu để kiểm thử",
        status=AssetStatus.IN_AUCTION,
        is_public=True,
        created_by=users["staff"].user_id,
    )
    db.add(asset)
    await db.flush()

    now = utcnow()
    session = AuctionSession(
        asset_id=asset.asset_id,
        auctioneer_id=users["auctioneer"].user_id,
        starting_price=Decimal("100000000"),
        bid_increment=Decimal("5000000"),
        deposit_amount=Decimal("20000000"),
        registration_deadline=now - timedelta(days=2),
        deposit_deadline=now - timedelta(days=1),
        start_time=now - timedelta(minutes=5),
        end_time=now + timedelta(minutes=minutes_left),
        status=SessionStatus.IN_PROGRESS,
        notice_content="Thông báo đấu giá mẫu",
    )
    db.add(session)
    await db.flush()

    registrations = []
    for i in range(1, bidder_count + 1):
        bidder = users[f"bidder{i}"]
        registrations.append(
            Registration(
                session_id=session.session_id,
                bidder_id=bidder.user_id,
                submitted_full_name=bidder.full_name,
                submitted_id_number=f"0010900{i:05d}",
                status=RegistrationStatus.APPROVED,
                bidder_alias=f"NTG-{i:02d}",
            )
        )
    db.add_all(registrations)
    await db.commit()
    return SeedData(users=users, session=session, registrations=registrations)


async def main() -> None:
    async with SessionLocal() as db:
        if await db.scalar(select(User).where(User.username == "admin")) is not None:
            print("Dữ liệu mẫu đã tồn tại, bỏ qua.")
        else:
            data = await seed(db)
            print(f"Đã tạo dữ liệu mẫu. Phiên đang diễn ra: {data.session.code}")
            print(f"Tài khoản: {', '.join(data.users)} / mật khẩu: {DEFAULT_PASSWORD}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
