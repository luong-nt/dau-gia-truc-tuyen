"""Nghiệp vụ tài sản (FR-05 - FR-07).

Trạng thái tài sản (quy ước đã thống nhất):
    tạo mới                        -> UPCOMING
    phiên chuyển IN_PROGRESS       -> IN_AUCTION   (module sessions tự cập nhật)
    kết quả CONFIRMED có người trúng -> ENDED      (module results)
    không thành / phiên bị hủy     -> UPCOMING     (để tổ chức lại)
    Nhân viên chủ động             -> SUSPENDED_CANCELLED
"""

from decimal import Decimal
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_activity
from app.core.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.core.pagination import Page, PageParams
from app.core.storage import DOCUMENT_FORMATS, IMAGE_FORMATS, resolve_path, save_upload
from app.db.enums import AssetStatus, FileType
from app.db.models import Asset, AssetOwner, Attachment, User
from app.modules.assets import repository
from app.modules.assets.permissions import can_view_asset, can_view_attachment, is_internal
from app.modules.assets.schemas import (
    AssetCreateRequest,
    AssetDetailOut,
    AssetOut,
    AssetOwnerOut,
    AssetOwnerRequest,
    AssetSessionOut,
    AssetStatusRequest,
    AssetUpdateRequest,
    AttachmentOut,
)
from app.modules.sessions import repository as session_repository

UPDATABLE_FIELDS = ("name", "description", "owner_id", "is_public")
ASSET_CODE_CONSTRAINT = "uq_assets_code"
ASSET_FILE_FORMATS = {FileType.ASSET_IMAGE: IMAGE_FORMATS, FileType.ASSET_DOCUMENT: DOCUMENT_FORMATS}
MEDIA_TYPES = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "pdf": "application/pdf"}
OWNER_ID_NUMBER_CONSTRAINT = "uq_asset_owners_id_number"
OWNER_FIELDS = ("owner_type", "name", "id_number", "representative_name", "phone", "email", "address")


def _violates(exc: IntegrityError, constraint: str) -> bool:
    """Chỉ nhận đúng ràng buộc unique cần xử lý; lỗi ràng buộc khác vẫn ném tiếp."""
    original = exc.orig
    candidates = (original, getattr(original, "__cause__", None), getattr(original, "diag", None))
    return any(getattr(c, "constraint_name", None) == constraint for c in candidates) or constraint in str(original)


async def _commit_unique(db: AsyncSession, constraint: str, error: ConflictError) -> None:
    """Commit; nếu hai yêu cầu đồng thời cùng vượt qua kiểm tra trùng thì DB chặn và trả 409 thay vì 500."""
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        if _violates(exc, constraint):
            raise error from exc
        raise


async def _detail(db: AsyncSession, asset: Asset, user: User | None) -> AssetDetailOut:
    internal = is_internal(user)
    owner = await repository.get_owner(db, asset.owner_id) if internal else None
    sessions = await repository.list_sessions_of_asset(db, asset.asset_id, include_draft=internal)
    attachments = await repository.list_attachments_of_asset(db, asset.asset_id)
    return AssetDetailOut(
        **AssetOut.model_validate(asset).model_dump(),
        owner=AssetOwnerOut.model_validate(owner) if owner else None,
        sessions=[AssetSessionOut.model_validate(s) for s in sessions],
        attachments=[AttachmentOut.model_validate(a) for a in attachments if can_view_attachment(asset, a, user)],
    )


async def _ensure_owner(db: AsyncSession, owner_id: int) -> None:
    if await repository.get_owner(db, owner_id) is None:
        raise BusinessRuleError("Không tìm thấy người có tài sản", code="OWNER_NOT_FOUND")


async def _load_for_update(db: AsyncSession, asset_id: int) -> Asset:
    asset = await repository.get_asset_for_update(db, asset_id)
    if asset is None:
        raise NotFoundError("Không tìm thấy tài sản")
    return asset


async def search_assets(
    db: AsyncSession,
    user: User | None,
    *,
    keyword: str | None,
    status: AssetStatus | None,
    min_price: int | None,
    max_price: int | None,
    page: PageParams,
) -> Page[AssetOut]:
    if min_price is not None and max_price is not None and min_price > max_price:
        raise BusinessRuleError("Giá thấp nhất không được lớn hơn giá cao nhất", code="INVALID_PRICE_RANGE")
    items, total = await repository.search_assets(
        db,
        keyword=keyword.strip() if keyword else None,
        status=status,
        min_price=Decimal(min_price) if min_price is not None else None,
        max_price=Decimal(max_price) if max_price is not None else None,
        only_public=not is_internal(user),
        offset=page.offset,
        limit=page.size,
    )
    return Page[AssetOut](
        items=[AssetOut.model_validate(a) for a in items], total=total, page=page.page, size=page.size
    )


async def get_asset_detail(db: AsyncSession, asset_id: int, user: User | None) -> AssetDetailOut:
    asset = await repository.get_asset(db, asset_id)
    if asset is None or not can_view_asset(asset, user):
        raise NotFoundError("Không tìm thấy tài sản")
    return await _detail(db, asset, user)


async def create_asset(db: AsyncSession, data: AssetCreateRequest, staff: User) -> AssetDetailOut:
    await _ensure_owner(db, data.owner_id)
    if await repository.get_by_code(db, data.asset_code) is not None:
        raise ConflictError("Mã tài sản đã tồn tại", code="ASSET_CODE_EXISTS")
    asset = Asset(**data.model_dump(), status=AssetStatus.UPCOMING, created_by=staff.user_id)
    duplicate = ConflictError("Mã tài sản đã tồn tại", code="ASSET_CODE_EXISTS")
    db.add(asset)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        if _violates(exc, ASSET_CODE_CONSTRAINT):
            raise duplicate from exc
        raise
    log_activity(
        db,
        user_id=staff.user_id,
        action="CREATE_ASSET",
        entity_type="asset",
        entity_id=asset.asset_id,
        new_value=asset.asset_code,
    )
    await _commit_unique(db, ASSET_CODE_CONSTRAINT, duplicate)
    await db.refresh(asset)
    return await _detail(db, asset, staff)


async def update_asset(db: AsyncSession, asset_id: int, data: AssetUpdateRequest, staff: User) -> AssetDetailOut:
    """FR-05: tài sản đang công khai thì mọi thay đổi phải có lý do; mỗi trường đổi ghi một dòng nhật ký."""
    asset = await _load_for_update(db, asset_id)
    if data.owner_id != asset.owner_id:
        await _ensure_owner(db, data.owner_id)
    changes = {
        field: (getattr(asset, field), getattr(data, field))
        for field in UPDATABLE_FIELDS
        if getattr(asset, field) != getattr(data, field)
    }
    reason = data.reason or None
    if changes and asset.is_public and reason is None:
        raise BusinessRuleError("Tài sản đã công khai, thay đổi phải có lý do", code="REASON_REQUIRED")
    for field, (old, new) in changes.items():
        setattr(asset, field, new)
        log_activity(
            db,
            user_id=staff.user_id,
            action="UPDATE_ASSET",
            entity_type="asset",
            entity_id=asset.asset_id,
            field_name=field,
            old_value=old,
            new_value=new,
            reason=reason,
        )
    await db.commit()
    return await _detail(db, asset, staff)


async def delete_asset(db: AsyncSession, asset_id: int, staff: User) -> None:
    """FR-06: chỉ xoá tài sản chưa gắn phiên nào; tệp đính kèm của tài sản bị xoá theo."""
    asset = await _load_for_update(db, asset_id)
    if await repository.has_sessions(db, asset_id):
        raise ConflictError("Tài sản đã có phiên đấu giá, chỉ được ngừng sử dụng", code="ASSET_HAS_SESSIONS")
    attachments = await repository.list_attachments_of_asset(db, asset_id)
    await repository.delete_attachments_of_asset(db, asset_id)
    log_activity(
        db,
        user_id=staff.user_id,
        action="DELETE_ASSET",
        entity_type="asset",
        entity_id=asset.asset_id,
        old_value=asset.asset_code,
    )
    await db.delete(asset)
    await db.commit()
    for attachment in attachments:
        _remove_file(attachment.file_url)


def _remove_file(file_url: str) -> None:
    """Xoá tệp sau khi đã commit; tệp đã mất trên đĩa thì bỏ qua."""
    try:
        resolve_path(file_url).unlink(missing_ok=True)
    except (OSError, BusinessRuleError):
        return


async def change_status(db: AsyncSession, asset_id: int, data: AssetStatusRequest, staff: User) -> AssetDetailOut:
    """FR-06: Nhân viên chỉ được chuyển UPCOMING -> SUSPENDED_CANCELLED, có lý do."""
    asset = await _load_for_update(db, asset_id)
    if data.status != AssetStatus.SUSPENDED_CANCELLED or asset.status != AssetStatus.UPCOMING:
        raise BusinessRuleError(
            "Chỉ được ngừng tài sản đang ở trạng thái sắp đấu giá", code="INVALID_ASSET_STATUS_TRANSITION"
        )
    if await session_repository.has_active_session(db, asset_id):
        raise ConflictError("Tài sản đang có phiên chưa kết thúc", code="ASSET_HAS_ACTIVE_SESSION")
    old = asset.status
    asset.status = AssetStatus.SUSPENDED_CANCELLED
    log_activity(
        db,
        user_id=staff.user_id,
        action="UPDATE_ASSET_STATUS",
        entity_type="asset",
        entity_id=asset.asset_id,
        field_name="status",
        old_value=old,
        new_value=asset.status,
        reason=data.reason,
    )
    await db.commit()
    return await _detail(db, asset, staff)


# ---------------- Người có tài sản (FR-05) ----------------


async def search_owners(db: AsyncSession, *, keyword: str | None, page: PageParams) -> Page[AssetOwnerOut]:
    items, total = await repository.search_owners(
        db, keyword=keyword.strip() if keyword else None, offset=page.offset, limit=page.size
    )
    return Page[AssetOwnerOut](
        items=[AssetOwnerOut.model_validate(o) for o in items], total=total, page=page.page, size=page.size
    )


async def get_owner(db: AsyncSession, owner_id: int) -> AssetOwnerOut:
    owner = await repository.get_owner(db, owner_id)
    if owner is None:
        raise NotFoundError("Không tìm thấy người có tài sản")
    return AssetOwnerOut.model_validate(owner)


async def _ensure_id_number_free(db: AsyncSession, id_number: str, owner_id: int | None = None) -> None:
    existing = await repository.get_owner_by_id_number(db, id_number)
    if existing is not None and existing.owner_id != owner_id:
        raise ConflictError("Số giấy tờ của người có tài sản đã tồn tại", code="OWNER_ID_NUMBER_EXISTS")


async def create_owner(db: AsyncSession, data: AssetOwnerRequest, staff: User) -> AssetOwnerOut:
    await _ensure_id_number_free(db, data.id_number)
    owner = AssetOwner(**data.model_dump())
    duplicate = ConflictError("Số giấy tờ của người có tài sản đã tồn tại", code="OWNER_ID_NUMBER_EXISTS")
    db.add(owner)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        if _violates(exc, OWNER_ID_NUMBER_CONSTRAINT):
            raise duplicate from exc
        raise
    log_activity(
        db,
        user_id=staff.user_id,
        action="CREATE_ASSET_OWNER",
        entity_type="asset_owner",
        entity_id=owner.owner_id,
        new_value=owner.name,
    )
    await _commit_unique(db, OWNER_ID_NUMBER_CONSTRAINT, duplicate)
    await db.refresh(owner)
    return AssetOwnerOut.model_validate(owner)


async def update_owner(db: AsyncSession, owner_id: int, data: AssetOwnerRequest, staff: User) -> AssetOwnerOut:
    """Mỗi trường thật sự thay đổi ghi một dòng nhật ký UPDATE_ASSET_OWNER."""
    owner = await repository.get_owner_for_update(db, owner_id)
    if owner is None:
        raise NotFoundError("Không tìm thấy người có tài sản")
    if data.id_number != owner.id_number:
        await _ensure_id_number_free(db, data.id_number, owner_id)
    for field in OWNER_FIELDS:
        old, new = getattr(owner, field), getattr(data, field)
        if old == new:
            continue
        setattr(owner, field, new)
        log_activity(
            db,
            user_id=staff.user_id,
            action="UPDATE_ASSET_OWNER",
            entity_type="asset_owner",
            entity_id=owner.owner_id,
            field_name=field,
            old_value=old,
            new_value=new,
        )
    await _commit_unique(
        db,
        OWNER_ID_NUMBER_CONSTRAINT,
        ConflictError("Số giấy tờ của người có tài sản đã tồn tại", code="OWNER_ID_NUMBER_EXISTS"),
    )
    return AssetOwnerOut.model_validate(owner)


# ---------------- Ảnh, tài liệu tài sản (FR-05, FR-07) ----------------


async def add_attachment(
    db: AsyncSession, asset_id: int, file: UploadFile, file_type: str, staff: User
) -> AttachmentOut:
    """Lưu tệp qua `save_upload`; ảnh chỉ JPG/PNG, tài liệu PDF/JPG/PNG. Lỗi ghi DB thì xoá tệp vừa lưu."""
    asset = await _load_for_update(db, asset_id)  # khoá dòng tài sản để display_order không trùng
    allowed = ASSET_FILE_FORMATS.get(file_type)
    if allowed is None:
        raise BusinessRuleError("Loại tệp phải là ASSET_IMAGE hoặc ASSET_DOCUMENT", code="INVALID_FILE_TYPE")
    stored = await save_upload(file, subdir=f"assets/{asset.asset_id}", allowed_formats=allowed)
    try:
        attachment = Attachment(
            asset_id=asset.asset_id,
            file_type=file_type,
            file_name=stored.file_name,
            file_url=stored.file_url,
            file_format=stored.file_format,
            file_size=stored.file_size,
            display_order=await repository.next_display_order(db, asset.asset_id),
        )
        db.add(attachment)
        await db.flush()
        log_activity(
            db,
            user_id=staff.user_id,
            action="ADD_ASSET_ATTACHMENT",
            entity_type="asset",
            entity_id=asset.asset_id,
            new_value=attachment.file_name,
        )
        await db.commit()
    except BaseException:
        await db.rollback()
        _remove_file(stored.file_url)
        raise
    await db.refresh(attachment)
    return AttachmentOut.model_validate(attachment)


async def get_attachment_file(
    db: AsyncSession, asset_id: int, attachment_id: int, user: User | None
) -> tuple[Path, str, str]:
    """Trả (đường dẫn thật, media type, tên tệp). Người công khai chỉ tải ảnh của tài sản đã công khai."""
    asset = await repository.get_asset(db, asset_id)
    attachment = await repository.get_attachment(db, asset_id, attachment_id) if asset else None
    if asset is None or attachment is None or not can_view_attachment(asset, attachment, user):
        raise NotFoundError("Không tìm thấy tệp")
    path = resolve_path(attachment.file_url)
    if not path.is_file():
        raise NotFoundError("Không tìm thấy tệp")
    media_type = MEDIA_TYPES.get((attachment.file_format or "").lower(), "application/octet-stream")
    return path, media_type, attachment.file_name


async def delete_attachment(db: AsyncSession, asset_id: int, attachment_id: int, staff: User) -> None:
    asset = await _load_for_update(db, asset_id)
    attachment = await repository.get_attachment(db, asset.asset_id, attachment_id)
    if attachment is None:
        raise NotFoundError("Không tìm thấy tệp")
    file_url = attachment.file_url
    log_activity(
        db,
        user_id=staff.user_id,
        action="DELETE_ASSET_ATTACHMENT",
        entity_type="asset",
        entity_id=asset.asset_id,
        old_value=attachment.file_name,
    )
    await db.delete(attachment)
    await db.commit()
    _remove_file(file_url)
