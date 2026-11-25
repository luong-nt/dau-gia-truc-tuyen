"""Nghiệp vụ hồ sơ đăng ký (FR-10 - FR-15).

Trạng thái hồ sơ:
    nộp mới                      -> PENDING
    PENDING -> APPROVED          chỉ khi 3 bước DOCUMENT/ELIGIBILITY/DEPOSIT_CHECK đều PASSED
                                 (dùng repository.all_checks_passed); sinh bidder_alias lúc này
    PENDING -> NEEDS_SUPPLEMENT  bắt buộc lý do + supplement_deadline
    PENDING -> REJECTED          bắt buộc lý do
    NEEDS_SUPPLEMENT -> PENDING  người tham gia nộp lại TRƯỚC hạn (submission_count + 1,
                                 tệp mới gắn submission_no = submission_count)
    Quá hạn bổ sung: chỉ chặn nộp lại, KHÔNG tự đổi trạng thái (reviewed_by là NOT NULL);
    nhân viên từ chối thủ công.

Mỗi quyết định ghi 1 dòng registration_reviews và 1 dòng activity_logs.
"""

import logging
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_activity
from app.core.clock import utcnow
from app.core.exceptions import AppError, BusinessRuleError, ConflictError, NotFoundError
from app.core.pagination import Page, PageParams
from app.core.storage import resolve_path, save_upload
from app.db.enums import FileType, RegistrationStatus, ReviewResult, ReviewType, SessionStatus, UserRole
from app.db.models import Attachment, AuctionSession, Registration, RegistrationReview, User
from app.modules.registrations import repository
from app.modules.registrations.permissions import ensure_can_view_eligible, ensure_owner_or_staff
from app.modules.registrations.schemas import (
    AttachmentOut,
    DecisionRequest,
    EligibleBidderOut,
    EligibleListOut,
    RegistrationDetailOut,
    RegistrationOut,
    RegistrationResubmitRequest,
    RegistrationSubmitRequest,
    ReviewCheckRequest,
    ReviewOut,
    StaffReviewOut,
)
from app.modules.reports import exporters
from app.modules.sessions import repository as session_repository

logger = logging.getLogger(__name__)


async def _registration_details(
    db: AsyncSession,
    registrations: list[Registration],
    *,
    staff: bool = False,
) -> list[RegistrationDetailOut]:
    ids = [registration.registration_id for registration in registrations]
    attachments, reviews = await repository.list_details(db, ids)
    attachments_by_id: dict[int, list[AttachmentOut]] = {registration_id: [] for registration_id in ids}
    reviews_by_id: dict[int, list[StaffReviewOut | ReviewOut]] = {registration_id: [] for registration_id in ids}
    for attachment in attachments:
        if attachment.registration_id is not None:
            attachments_by_id[attachment.registration_id].append(AttachmentOut.model_validate(attachment))
    for review in reviews:
        reviews_by_id[review.registration_id].append(
            StaffReviewOut.model_validate(review) if staff else ReviewOut.model_validate(review)
        )
    return [
        RegistrationDetailOut(
            **RegistrationOut.model_validate(registration).model_dump(exclude={"bidder_id"}),
            session_code=f"PDG-{registration.session_id}",
            attachments=attachments_by_id[registration.registration_id],
            reviews=reviews_by_id[registration.registration_id],
        )
        for registration in registrations
    ]


def _cleanup_uploads(subdir: str | None, existing_files: set[Path]) -> None:
    """Dọn tệp của lần nộp thất bại, kể cả tệp ghi dở; giữ nguyên tệp đã có."""
    if subdir is None:
        return
    try:
        directory = resolve_path(subdir)
        if directory.is_dir():
            for path in directory.iterdir():
                if path in existing_files:
                    continue
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    logger.warning("Không thể xóa tệp của lần nộp hồ sơ thất bại", exc_info=True)
            if not any(directory.iterdir()):
                directory.rmdir()
    except OSError:
        logger.warning("Không thể dọn thư mục của lần nộp hồ sơ thất bại", exc_info=True)


def _is_duplicate_registration(exc: IntegrityError) -> bool:
    """Chỉ chuyển vi phạm ràng buộc hồ sơ trùng thành lỗi nghiệp vụ 409."""
    constraint = "uq_registrations_session_bidder"
    original = exc.orig
    cause = getattr(original, "__cause__", None)
    diagnostic = getattr(original, "diag", None)
    return (
        getattr(cause, "constraint_name", None) == constraint
        or getattr(original, "constraint_name", None) == constraint
        or getattr(diagnostic, "constraint_name", None) == constraint
    )


async def submit_registration(
    db: AsyncSession,
    session_id: int,
    bidder: User,
    data: RegistrationSubmitRequest,
    identity_documents: list[UploadFile],
    deposit_receipt: UploadFile | None = None,
) -> RegistrationDetailOut:
    subdir: str | None = None
    existing_files: set[Path] = set()
    try:
        session = await session_repository.get_session_for_update(db, session_id)
        if session is None:
            raise NotFoundError("Không tìm thấy phiên đấu giá")
        now = utcnow()
        if session.status != SessionStatus.OPEN_FOR_REGISTRATION or now >= session.registration_deadline:
            raise BusinessRuleError("Phiên đã đóng nhận hồ sơ đăng ký", code="REGISTRATION_CLOSED")
        if await repository.get_registration_for_bidder(db, session_id, bidder.user_id) is not None:
            raise ConflictError("Bạn đã có hồ sơ đăng ký cho phiên này", code="ALREADY_REGISTERED")
        if not identity_documents:
            raise BusinessRuleError("Cần tải lên ít nhất một giấy tờ định danh", code="IDENTITY_DOCUMENT_REQUIRED")

        registration = Registration(
            session_id=session_id,
            bidder_id=bidder.user_id,
            **data.model_dump(),
            status=RegistrationStatus.PENDING,
            submission_count=1,
            submitted_at=now,
        )
        db.add(registration)
        await db.flush()
        upload_subdir = f"registrations/{registration.registration_id}"
        directory = resolve_path(upload_subdir)
        if directory.is_dir():
            existing_files = set(directory.iterdir())
        subdir = upload_subdir
        uploads = [(file, FileType.IDENTITY_DOCUMENT) for file in identity_documents]
        if deposit_receipt is not None:
            uploads.append((deposit_receipt, FileType.DEPOSIT_RECEIPT))
        for display_order, (file, file_type) in enumerate(uploads, start=1):
            stored = await save_upload(file, subdir=subdir)
            db.add(
                Attachment(
                    registration_id=registration.registration_id,
                    asset_id=None,
                    submission_no=1,
                    file_type=file_type,
                    display_order=display_order,
                    file_name=stored.file_name,
                    file_url=stored.file_url,
                    file_format=stored.file_format,
                    file_size=stored.file_size,
                )
            )
        log_activity(
            db,
            user_id=bidder.user_id,
            action="SUBMIT_REGISTRATION",
            entity_type="registration",
            entity_id=registration.registration_id,
        )
        await db.flush()
        output = (await _registration_details(db, [registration]))[0]
        await db.commit()
    except BaseException as exc:
        try:
            await db.rollback()
        finally:
            _cleanup_uploads(subdir, existing_files)
        if isinstance(exc, IntegrityError) and _is_duplicate_registration(exc):
            raise ConflictError("Bạn đã có hồ sơ đăng ký cho phiên này", code="ALREADY_REGISTERED") from exc
        raise
    return output


async def list_my_registrations(
    db: AsyncSession,
    bidder: User,
    *,
    status: RegistrationStatus | None,
    page: PageParams,
) -> Page[RegistrationDetailOut]:
    registrations, total = await repository.list_my_registrations(
        db, bidder.user_id, status=status, offset=page.offset, limit=page.size
    )
    return Page[RegistrationDetailOut](
        items=await _registration_details(db, registrations), total=total, page=page.page, size=page.size
    )


async def get_attachment_download(
    db: AsyncSession, registration_id: int, attachment_id: int, user: User
) -> tuple[Path, str]:
    registration = await repository.get_registration(db, registration_id)
    if registration is None:
        raise NotFoundError("Không tìm thấy hồ sơ đăng ký")
    ensure_owner_or_staff(registration, user)
    attachment = await repository.get_attachment(db, registration_id, attachment_id)
    if attachment is None:
        raise NotFoundError("Không tìm thấy tệp đính kèm của hồ sơ")
    path = resolve_path(attachment.file_url)
    if not path.is_file():
        raise NotFoundError("Không tìm thấy tệp trên hệ thống lưu trữ")
    return path, attachment.file_name


def format_alias(number: int) -> str:
    """Mã ẩn danh hiển thị trong phòng đấu giá, ví dụ NTG-01 (FR-19)."""
    return f"NTG-{number:02d}"


async def list_registrations(
    db: AsyncSession,
    *,
    session_id: int | None,
    status: RegistrationStatus | None,
    keyword: str | None,
    page: PageParams,
) -> Page[RegistrationDetailOut]:
    registrations, total = await repository.list_registrations(
        db,
        session_id=session_id,
        status=status,
        keyword=keyword,
        offset=page.offset,
        limit=page.size,
    )
    return Page[RegistrationDetailOut](
        items=await _registration_details(db, registrations, staff=True), total=total, page=page.page, size=page.size
    )


async def get_registration_detail(db: AsyncSession, registration_id: int, user: User) -> RegistrationDetailOut:
    registration = await repository.get_registration(db, registration_id)
    if registration is None:
        raise NotFoundError("Không tìm thấy hồ sơ đăng ký")
    ensure_owner_or_staff(registration, user)
    return (await _registration_details(db, [registration], staff=user.role == UserRole.STAFF))[0]


async def _load_locked(db: AsyncSession, registration_id: int) -> tuple[Registration, AuctionSession]:
    """Luôn khóa phiên trước hồ sơ để thống nhất thứ tự với nộp hồ sơ và cấp mã."""
    registration = await repository.get_registration(db, registration_id)
    if registration is None:
        raise NotFoundError("Không tìm thấy hồ sơ đăng ký")
    session = await session_repository.get_session_for_update(db, registration.session_id)
    if session is None:
        raise NotFoundError("Không tìm thấy phiên đấu giá")
    registration = await repository.get_registration_for_update(db, registration_id)
    if registration is None:
        raise NotFoundError("Không tìm thấy hồ sơ đăng ký")
    return registration, session


def _require_pending(registration: Registration) -> None:
    if registration.status != RegistrationStatus.PENDING:
        raise BusinessRuleError("Hồ sơ không ở trạng thái chờ duyệt", code="INVALID_REGISTRATION_STATUS")


def _require_reason(reason: str | None) -> None:
    if not (reason and reason.strip()):
        raise BusinessRuleError("Cần nhập lý do", code="REASON_REQUIRED")


async def record_check(
    db: AsyncSession,
    registration_id: int,
    data: ReviewCheckRequest,
    staff: User,
) -> StaffReviewOut:
    registration, _ = await _load_locked(db, registration_id)
    _require_pending(registration)
    if data.result == ReviewResult.FAILED:
        _require_reason(data.reason)
    review = RegistrationReview(registration_id=registration_id, reviewed_by=staff.user_id, **data.model_dump())
    db.add(review)
    actions = {
        ReviewType.DOCUMENT_CHECK: "CHECK_DOCUMENT",
        ReviewType.ELIGIBILITY_CHECK: "CHECK_ELIGIBILITY",
        ReviewType.DEPOSIT_CHECK: "CONFIRM_DEPOSIT",
    }
    log_activity(
        db,
        user_id=staff.user_id,
        action=actions[data.review_type],
        entity_type="registration",
        entity_id=registration_id,
        new_value=data.result,
        reason=data.reason,
    )
    await db.flush()
    output = StaffReviewOut.model_validate(review)
    await db.commit()
    return output


async def decide(
    db: AsyncSession,
    registration_id: int,
    data: DecisionRequest,
    staff: User,
) -> RegistrationDetailOut:
    registration, session = await _load_locked(db, registration_id)
    now = utcnow()
    expired_reject = (
        data.decision == ReviewType.REJECT
        and registration.status == RegistrationStatus.NEEDS_SUPPLEMENT
        and registration.supplement_deadline is not None
        and now >= registration.supplement_deadline
    )
    if not expired_reject:
        _require_pending(registration)
    if session.status in (
        SessionStatus.IN_PROGRESS,
        SessionStatus.PAUSED,
        SessionStatus.ENDED,
        SessionStatus.CANCELLED,
    ):
        raise BusinessRuleError("Phiên không còn cho phép xét duyệt hồ sơ", code="SESSION_NOT_ACCEPTING_REVIEWS")
    old_status = registration.status
    if data.decision == ReviewType.APPROVE:
        results = await repository.latest_check_results(db, registration_id)
        if not repository.all_checks_passed(results):
            raise BusinessRuleError("Chưa đạt đủ ba bước đối chiếu", code="CHECKS_NOT_PASSED", details=results)
        registration.bidder_alias = format_alias(await repository.next_alias_number(db, session.session_id))
        registration.status = RegistrationStatus.APPROVED
        action = "APPROVE_REGISTRATION"
    else:
        _require_reason(data.reason)
        if data.decision == ReviewType.REQUEST_SUPPLEMENT:
            deadline = data.supplement_deadline
            if deadline is None or deadline <= now or deadline >= session.start_time:
                raise BusinessRuleError(
                    "Hạn bổ sung phải sau hiện tại và trước giờ bắt đầu phiên", code="INVALID_SUPPLEMENT_DEADLINE"
                )
            registration.status = RegistrationStatus.NEEDS_SUPPLEMENT
            registration.supplement_deadline = deadline
            action = "REQUEST_SUPPLEMENT"
        else:
            registration.status = RegistrationStatus.REJECTED
            action = "REJECT_REGISTRATION"
    db.add(
        RegistrationReview(
            registration_id=registration_id,
            reviewed_by=staff.user_id,
            review_type=data.decision,
            result=None,
            reason=data.reason,
        )
    )
    log_activity(
        db,
        user_id=staff.user_id,
        action=action,
        entity_type="registration",
        entity_id=registration_id,
        field_name="status",
        old_value=old_status,
        new_value=registration.status,
        reason=data.reason,
    )
    await db.flush()
    output = (await _registration_details(db, [registration], staff=True))[0]
    await db.commit()
    return output


async def resubmit(
    db: AsyncSession,
    registration_id: int,
    data: RegistrationResubmitRequest,
    bidder: User,
    identity_documents: list[UploadFile],
    deposit_receipt: UploadFile | None,
) -> RegistrationDetailOut:
    subdir: str | None = None
    existing_files: set[Path] = set()
    try:
        registration, _ = await _load_locked(db, registration_id)
        ensure_owner_or_staff(registration, bidder)
        if registration.status != RegistrationStatus.NEEDS_SUPPLEMENT:
            raise BusinessRuleError("Hồ sơ không ở trạng thái cần bổ sung", code="INVALID_REGISTRATION_STATUS")
        if registration.supplement_deadline is None or utcnow() >= registration.supplement_deadline:
            raise BusinessRuleError("Đã hết hạn bổ sung hồ sơ", code="SUPPLEMENT_EXPIRED")
        updates = data.model_dump(exclude_unset=True)
        if not updates and not identity_documents and deposit_receipt is None:
            raise BusinessRuleError("Chưa có thông tin hoặc tệp bổ sung", code="NOTHING_TO_UPDATE")
        for field, value in updates.items():
            setattr(registration, field, value)
        registration.submission_count += 1
        uploads = [(file, FileType.IDENTITY_DOCUMENT) for file in identity_documents]
        if deposit_receipt is not None:
            uploads.append((deposit_receipt, FileType.DEPOSIT_RECEIPT))
        subdir = f"registrations/{registration_id}"
        directory = resolve_path(subdir)
        if directory.is_dir():
            existing_files = set(directory.iterdir())
        for display_order, (file, file_type) in enumerate(uploads, start=1):
            stored = await save_upload(file, subdir=subdir)
            db.add(
                Attachment(
                    registration_id=registration_id,
                    asset_id=None,
                    submission_no=registration.submission_count,
                    file_type=file_type,
                    display_order=display_order,
                    file_name=stored.file_name,
                    file_url=stored.file_url,
                    file_format=stored.file_format,
                    file_size=stored.file_size,
                )
            )
        old_status = registration.status
        registration.status = RegistrationStatus.PENDING
        log_activity(
            db,
            user_id=bidder.user_id,
            action="RESUBMIT_REGISTRATION",
            entity_type="registration",
            entity_id=registration_id,
            field_name="status",
            old_value=old_status,
            new_value=registration.status,
        )
        await db.flush()
        output = (await _registration_details(db, [registration]))[0]
        await db.commit()
        return output
    except BaseException:
        try:
            await db.rollback()
        finally:
            _cleanup_uploads(subdir, existing_files)
        raise


async def _load_eligible(
    db: AsyncSession,
    session_id: int,
    user: User,
) -> tuple[EligibleListOut, list[Registration]]:
    session = await session_repository.get_session(db, session_id)
    if session is None:
        raise NotFoundError("Không tìm thấy phiên đấu giá")
    ensure_can_view_eligible(session, user)
    asset = await session_repository.get_asset(db, session.asset_id)
    if asset is None:
        raise NotFoundError("Không tìm thấy tài sản")
    rows = await repository.list_eligible_bidders(db, session_id)
    items = [
        EligibleBidderOut(
            registration_id=registration.registration_id,
            bidder_alias=registration.bidder_alias,
            full_name=registration.submitted_full_name,
            approved_at=approved_at,
        )
        for registration, approved_at in rows
    ]
    return EligibleListOut(
        session_id=session_id, session_code=session.code, asset_name=asset.name, total=len(items), items=items
    ), [registration for registration, _ in rows]


async def list_eligible_bidders(db: AsyncSession, session_id: int, user: User) -> EligibleListOut:
    output, _ = await _load_eligible(db, session_id, user)
    return output


async def export_eligible_bidders(
    db: AsyncSession,
    session_id: int,
    user: User,
    *,
    format: str,
    include_identity: bool,
) -> bytes:
    output, registrations = await _load_eligible(db, session_id, user)
    if format == "csv":
        headers = ["STT", "Mã tham gia", "Họ tên"]
        if include_identity:
            headers.append("Số giấy tờ")
        rows = [
            [index, registration.bidder_alias, registration.submitted_full_name]
            + ([registration.submitted_id_number] if include_identity else [])
            for index, registration in enumerate(registrations, start=1)
        ]
        content = exporters.to_csv(headers, rows)
    else:
        context = {
            "session_code": output.session_code,
            "asset_name": output.asset_name,
            "rows": [
                dict(
                    bidder_alias=registration.bidder_alias,
                    full_name=registration.submitted_full_name,
                    id_number=registration.submitted_id_number if include_identity else None,
                )
                for registration in registrations
            ],
            "include_identity": include_identity,
            "generated_at": utcnow().strftime("%d/%m/%Y %H:%M"),
            "generated_by": user.full_name,
        }
        try:
            content = exporters.render_pdf("eligible_list.html", context)
        except (OSError, ImportError) as exc:
            raise AppError(
                "Không thể xuất PDF vì thiếu thư viện hệ thống. Vui lòng xuất CSV hoặc chạy bằng Docker.",
                code="PDF_ENGINE_UNAVAILABLE",
                status_code=503,
            ) from exc
    log_activity(
        db,
        user_id=user.user_id,
        action="EXPORT_ELIGIBLE_LIST",
        entity_type="auction_session",
        entity_id=session_id,
        new_value=format + ("+identity" if include_identity else ""),
    )
    await db.commit()
    return content
