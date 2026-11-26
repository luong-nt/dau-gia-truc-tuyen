from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

from app.core.money import Money
from app.db.enums import AssetStatus, OwnerType

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
AssetCode = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]
RequiredReason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class AssetOut(BaseModel):
    """Thông tin tài sản hiển thị công khai (không có thông tin người có tài sản)."""

    model_config = ConfigDict(from_attributes=True)

    asset_id: int
    asset_code: str
    name: str
    description: str | None
    status: str
    is_public: bool
    created_at: datetime


class AssetOwnerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    owner_id: int
    owner_type: str
    name: str
    id_number: str
    representative_name: str | None
    phone: str | None
    email: str | None
    address: str | None
    created_at: datetime


class AssetSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    session_id: int
    code: str
    status: str
    starting_price: Money
    start_time: datetime
    end_time: datetime


class AttachmentOut(BaseModel):
    """Không trả `file_url` (đường dẫn lưu trữ nội bộ)."""

    model_config = ConfigDict(from_attributes=True)

    attachment_id: int
    asset_id: int
    file_type: str
    file_name: str
    file_format: str | None
    file_size: int | None
    display_order: int | None
    uploaded_at: datetime


class AssetDetailOut(AssetOut):
    owner: AssetOwnerOut | None
    sessions: list[AssetSessionOut]
    attachments: list[AttachmentOut]


class AssetCreateRequest(BaseModel):
    asset_code: AssetCode
    owner_id: int
    name: Name
    description: str | None = Field(default=None, max_length=5000)
    is_public: bool = False


class AssetUpdateRequest(BaseModel):
    """FR-05: không đổi `asset_code`, `status` qua API này (gửi kèm thì bị bỏ qua)."""

    name: Name
    description: str | None = Field(default=None, max_length=5000)
    owner_id: int
    is_public: bool
    reason: Reason | None = None


class AssetStatusRequest(BaseModel):
    status: AssetStatus
    reason: RequiredReason


IdNumber = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20)]


class AssetOwnerRequest(BaseModel):
    """FR-05: thông tin người có tài sản (dùng cho thêm mới và cập nhật, gửi đủ các trường)."""

    owner_type: OwnerType
    name: Name
    id_number: IdNumber
    representative_name: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, pattern=r"^[0-9+]{9,15}$")
    email: EmailStr | None = Field(default=None, max_length=100)
    address: str | None = Field(default=None, max_length=255)
