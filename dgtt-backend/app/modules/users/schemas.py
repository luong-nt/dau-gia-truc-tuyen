from pydantic import BaseModel, EmailStr, Field

from app.db.enums import UserRole, UserStatus


class CreateUserRequest(BaseModel):
    """FR-04: Quản trị viên tạo tài khoản nội bộ."""

    role: UserRole
    full_name: str = Field(min_length=1, max_length=100)
    email: EmailStr = Field(max_length=100)
    phone: str | None = Field(default=None, pattern=r"^[0-9+]{9,15}$")
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.]+$")
    password: str = Field(min_length=8, max_length=128)


class ChangeRoleRequest(BaseModel):
    role: UserRole
    reason: str = Field(min_length=1, max_length=500)


class ChangeStatusRequest(BaseModel):
    status: UserStatus
    reason: str = Field(min_length=1, max_length=500)
