from datetime import datetime

from sqlalchemy import Integer, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import RegistrationStatus, ReviewResult, ReviewType
from app.db.models import Attachment, Registration, RegistrationReview

REQUIRED_CHECKS = (
    ReviewType.DOCUMENT_CHECK,
    ReviewType.ELIGIBILITY_CHECK,
    ReviewType.DEPOSIT_CHECK,
)


async def get_registration(db: AsyncSession, registration_id: int) -> Registration | None:
    return await db.get(Registration, registration_id)


async def get_registration_for_update(db: AsyncSession, registration_id: int) -> Registration | None:
    return await db.scalar(
        select(Registration)
        .where(Registration.registration_id == registration_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


async def list_registrations(
    db: AsyncSession,
    *,
    session_id: int | None,
    status: RegistrationStatus | None,
    keyword: str | None,
    offset: int,
    limit: int,
) -> tuple[list[Registration], int]:
    conditions = []
    if session_id is not None:
        conditions.append(Registration.session_id == session_id)
    if status is not None:
        conditions.append(Registration.status == status)
    if keyword:
        conditions.append(
            or_(
                Registration.submitted_full_name.icontains(keyword, autoescape=True),
                Registration.submitted_id_number.icontains(keyword, autoescape=True),
            )
        )
    total = await db.scalar(select(func.count()).select_from(Registration).where(*conditions))
    rows = await db.scalars(
        select(Registration)
        .where(*conditions)
        .order_by(Registration.submitted_at.desc(), Registration.registration_id.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(rows), int(total or 0)


async def get_registration_for_bidder(db: AsyncSession, session_id: int, bidder_id: int) -> Registration | None:
    return await db.scalar(
        select(Registration).where(Registration.session_id == session_id, Registration.bidder_id == bidder_id)
    )


async def list_my_registrations(
    db: AsyncSession,
    bidder_id: int,
    *,
    status: RegistrationStatus | None,
    offset: int,
    limit: int,
) -> tuple[list[Registration], int]:
    conditions = [Registration.bidder_id == bidder_id]
    if status is not None:
        conditions.append(Registration.status == status)
    total = await db.scalar(select(func.count()).select_from(Registration).where(*conditions))
    rows = await db.scalars(
        select(Registration)
        .where(*conditions)
        .order_by(Registration.submitted_at.desc(), Registration.registration_id.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(rows), int(total or 0)


async def list_details(
    db: AsyncSession, registration_ids: list[int]
) -> tuple[list[Attachment], list[RegistrationReview]]:
    """Lấy tệp và phản hồi theo lô, giữ thứ tự ổn định cho mỗi hồ sơ."""
    if not registration_ids:
        return [], []
    attachments = await db.scalars(
        select(Attachment)
        .where(Attachment.registration_id.in_(registration_ids))
        .order_by(Attachment.submission_no, Attachment.display_order, Attachment.attachment_id)
    )
    reviews = await db.scalars(
        select(RegistrationReview)
        .where(RegistrationReview.registration_id.in_(registration_ids))
        .order_by(RegistrationReview.reviewed_at, RegistrationReview.review_id)
    )
    return list(attachments), list(reviews)


async def get_attachment(db: AsyncSession, registration_id: int, attachment_id: int) -> Attachment | None:
    return await db.scalar(
        select(Attachment).where(
            Attachment.registration_id == registration_id, Attachment.attachment_id == attachment_id
        )
    )


async def latest_check_results(db: AsyncSession, registration_id: int) -> dict[str, str | None]:
    """Kết quả MỚI NHẤT của từng bước kiểm tra bắt buộc (dùng trước khi APPROVE - FR-12)."""
    results: dict[str, str | None] = {}
    for check in REQUIRED_CHECKS:
        results[check] = await db.scalar(
            select(RegistrationReview.result)
            .where(
                RegistrationReview.registration_id == registration_id,
                RegistrationReview.review_type == check,
            )
            .order_by(RegistrationReview.reviewed_at.desc(), RegistrationReview.review_id.desc())
            .limit(1)
        )
    return results


def all_checks_passed(results: dict[str, str | None]) -> bool:
    return all(results.get(c) == ReviewResult.PASSED for c in REQUIRED_CHECKS)


async def next_alias_number(db: AsyncSession, session_id: int) -> int:
    count = await db.scalar(
        select(func.count()).where(Registration.session_id == session_id, Registration.bidder_alias.is_not(None))
    )
    return int(count or 0) + 1


async def list_eligible_bidders(db: AsyncSession, session_id: int) -> list[tuple[Registration, datetime | None]]:
    """Lấy hồ sơ đã duyệt và thời điểm duyệt mới nhất, sắp mã tham gia theo số."""
    approved_at = (
        select(RegistrationReview.reviewed_at)
        .where(
            RegistrationReview.registration_id == Registration.registration_id,
            RegistrationReview.review_type == ReviewType.APPROVE,
        )
        .order_by(RegistrationReview.reviewed_at.desc(), RegistrationReview.review_id.desc())
        .limit(1)
        .correlate(Registration)
        .scalar_subquery()
    )
    rows = await db.execute(
        select(Registration, approved_at)
        .where(Registration.session_id == session_id, Registration.status == RegistrationStatus.APPROVED)
        .order_by(cast(func.split_part(Registration.bidder_alias, "-", 2), Integer), Registration.registration_id)
    )
    return [(registration, approved_at) for registration, approved_at in rows]
