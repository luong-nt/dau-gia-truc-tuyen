from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from fastapi.responses import FileResponse

from app.core.deps import REFRESHED_TOKEN_HEADER, DbSession, OptionalUser, require_roles
from app.core.pagination import Page, Pagination
from app.db.enums import AssetStatus, UserRole
from app.db.models import User
from app.modules.assets import service
from app.modules.assets.schemas import (
    AssetCreateRequest,
    AssetDetailOut,
    AssetOut,
    AssetOwnerOut,
    AssetOwnerRequest,
    AssetStatusRequest,
    AssetUpdateRequest,
    AttachmentOut,
)

router = APIRouter(tags=["Tài sản đấu giá (FR-05 - FR-07)"])
StaffUser = Annotated[User, Depends(require_roles(UserRole.STAFF))]


# ---------------- Người có tài sản: chỉ Nhân viên (FR-05) ----------------


@router.get("/asset-owners", response_model=Page[AssetOwnerOut])
async def search_owners(
    staff: StaffUser, db: DbSession, page: Pagination, keyword: str | None = None
) -> Page[AssetOwnerOut]:
    return await service.search_owners(db, keyword=keyword, page=page)


@router.get("/asset-owners/{owner_id}", response_model=AssetOwnerOut)
async def get_owner(owner_id: int, staff: StaffUser, db: DbSession) -> AssetOwnerOut:
    return await service.get_owner(db, owner_id)


@router.post("/asset-owners", response_model=AssetOwnerOut, status_code=status.HTTP_201_CREATED)
async def create_owner(data: AssetOwnerRequest, staff: StaffUser, db: DbSession) -> AssetOwnerOut:
    return await service.create_owner(db, data, staff)


@router.put("/asset-owners/{owner_id}", response_model=AssetOwnerOut)
async def update_owner(owner_id: int, data: AssetOwnerRequest, staff: StaffUser, db: DbSession) -> AssetOwnerOut:
    return await service.update_owner(db, owner_id, data, staff)


# ---------------- Tài sản (FR-05 - FR-07) ----------------


@router.get("/assets", response_model=Page[AssetOut])
async def search_assets(
    db: DbSession,
    user: OptionalUser,
    page: Pagination,
    keyword: str | None = None,
    status: AssetStatus | None = None,
    min_price: Annotated[int | None, Query(ge=0)] = None,
    max_price: Annotated[int | None, Query(ge=0)] = None,
) -> Page[AssetOut]:
    """FR-07: Khách/Người tham gia/Đấu giá viên chỉ thấy tài sản đã công khai."""
    return await service.search_assets(
        db, user, keyword=keyword, status=status, min_price=min_price, max_price=max_price, page=page
    )


@router.get("/assets/{asset_id}", response_model=AssetDetailOut)
async def get_asset(asset_id: int, db: DbSession, user: OptionalUser) -> AssetDetailOut:
    return await service.get_asset_detail(db, asset_id, user)


@router.post("/assets", response_model=AssetDetailOut, status_code=status.HTTP_201_CREATED)
async def create_asset(data: AssetCreateRequest, staff: StaffUser, db: DbSession) -> AssetDetailOut:
    return await service.create_asset(db, data, staff)


@router.put("/assets/{asset_id}", response_model=AssetDetailOut)
async def update_asset(asset_id: int, data: AssetUpdateRequest, staff: StaffUser, db: DbSession) -> AssetDetailOut:
    return await service.update_asset(db, asset_id, data, staff)


@router.delete("/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_asset(asset_id: int, staff: StaffUser, db: DbSession) -> None:
    """Trả None để FastAPI giữ header X-Access-Token do dependency đặt (NFR-04)."""
    await service.delete_asset(db, asset_id, staff)


@router.patch("/assets/{asset_id}/status", response_model=AssetDetailOut)
async def change_asset_status(
    asset_id: int, data: AssetStatusRequest, staff: StaffUser, db: DbSession
) -> AssetDetailOut:
    """FR-06: ngừng tài sản (SUSPENDED_CANCELLED), bắt buộc có lý do."""
    return await service.change_status(db, asset_id, data, staff)


# ---------------- Ảnh, tài liệu tài sản (FR-05, FR-07) ----------------


@router.post("/assets/{asset_id}/attachments", response_model=AttachmentOut, status_code=status.HTTP_201_CREATED)
async def upload_attachment(
    asset_id: int,
    staff: StaffUser,
    db: DbSession,
    file: Annotated[UploadFile, File()],
    file_type: Annotated[str, Form()],
) -> AttachmentOut:
    return await service.add_attachment(db, asset_id, file, file_type, staff)


@router.get("/assets/{asset_id}/attachments/{attachment_id}", response_class=FileResponse)
async def download_attachment(
    asset_id: int, attachment_id: int, db: DbSession, user: OptionalUser, response: Response
) -> FileResponse:
    """Tải tệp qua kiểm tra quyền (AGENTS.md 4.11); giữ header X-Access-Token khi có token (NFR-04)."""
    path, media_type, file_name = await service.get_attachment_file(db, asset_id, attachment_id, user)
    headers = {}
    if REFRESHED_TOKEN_HEADER in response.headers:
        headers[REFRESHED_TOKEN_HEADER] = response.headers[REFRESHED_TOKEN_HEADER]
    return FileResponse(path, media_type=media_type, filename=file_name, headers=headers)


@router.delete(
    "/assets/{asset_id}/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response
)
async def delete_attachment(asset_id: int, attachment_id: int, staff: StaffUser, db: DbSession) -> None:
    await service.delete_attachment(db, asset_id, attachment_id, staff)
