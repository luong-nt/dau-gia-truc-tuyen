from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: int
    role: str
    username: str
    email: str
    phone: str | None
    full_name: str
    status: str
    created_at: datetime


class RegisterRequest(BaseModel):
    """FR-01: Khách tạo tài khoản Người tham gia đấu giá."""

    full_name: str = Field(min_length=1, max_length=100)
    email: EmailStr = Field(max_length=100)
    phone: str | None = Field(default=None, pattern=r"^[0-9+]{9,15}$")
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.]+$")
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    """FR-02: đăng nhập bằng tên đăng nhập hoặc email."""

    login: str = Field(min_length=1, max_length=100, description="Tên đăng nhập hoặc email")
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class UpdateProfileRequest(BaseModel):
    """FR-03: cập nhật thông tin liên hệ. Không ảnh hưởng hồ sơ đã nộp."""

    full_name: str | None = Field(default=None, min_length=1, max_length=100)
    email: EmailStr | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, pattern=r"^[0-9+]{9,15}$")


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)
