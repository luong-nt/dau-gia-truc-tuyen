"""Nghiệp vụ tài khoản cá nhân: đăng ký, đăng nhập, hồ sơ, đổi mật khẩu (FR-01 - FR-03)."""

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_activity
from app.core.config import get_settings
from app.core.exceptions import ConflictError, ForbiddenError, UnauthorizedError
from app.core.security import create_access_token, hash_password, verify_password
from app.db.enums import UserRole, UserStatus
from app.db.models import User
from app.modules.auth.schemas import (
    ChangePasswordRequest,
    RegisterRequest,
    TokenResponse,
    UpdateProfileRequest,
    UserOut,
)


async def ensure_unique_account(
    db: AsyncSession,
    *,
    username: str | None = None,
    email: str | None = None,
    exclude_user_id: int | None = None,
) -> None:
    if username is not None:
        stmt = select(User.user_id).where(func.lower(User.username) == username.lower())
        if exclude_user_id is not None:
            stmt = stmt.where(User.user_id != exclude_user_id)
        if await db.scalar(stmt) is not None:
            raise ConflictError("Tên đăng nhập đã được sử dụng", code="USERNAME_TAKEN")
    if email is not None:
        stmt = select(User.user_id).where(func.lower(User.email) == email.lower())
        if exclude_user_id is not None:
            stmt = stmt.where(User.user_id != exclude_user_id)
        if await db.scalar(stmt) is not None:
            raise ConflictError("Email đã được sử dụng", code="EMAIL_TAKEN")


async def register_bidder(db: AsyncSession, data: RegisterRequest) -> User:
    await ensure_unique_account(db, username=data.username, email=data.email)
    user = User(
        role=UserRole.BIDDER,
        username=data.username,
        email=data.email.lower(),
        phone=data.phone,
        full_name=data.full_name.strip(),
        password_hash=hash_password(data.password),
        status=UserStatus.ACTIVE,
    )
    db.add(user)
    await db.flush()
    log_activity(db, user_id=user.user_id, action="REGISTER", entity_type="user", entity_id=user.user_id)
    await db.commit()
    await db.refresh(user)
    return user


async def login(db: AsyncSession, login_value: str, password: str) -> TokenResponse:
    user = await db.scalar(
        select(User).where(
            or_(
                func.lower(User.username) == login_value.lower(),
                func.lower(User.email) == login_value.lower(),
            )
        )
    )
    if user is None or not verify_password(password, user.password_hash):
        log_activity(
            db,
            user_id=user.user_id if user else None,
            action="LOGIN_FAILED",
            entity_type="user",
            entity_id=user.user_id if user else None,
        )
        await db.commit()
        raise UnauthorizedError("Tên đăng nhập hoặc mật khẩu không đúng", code="INVALID_CREDENTIALS")
    if user.status != UserStatus.ACTIVE:
        raise ForbiddenError("Tài khoản đã bị khóa", code="ACCOUNT_LOCKED")

    log_activity(db, user_id=user.user_id, action="LOGIN", entity_type="user", entity_id=user.user_id)
    await db.commit()
    return TokenResponse(
        access_token=create_access_token(user.user_id, user.role),
        expires_in=get_settings().access_token_expire_minutes * 60,
        user=UserOut.model_validate(user),
    )


async def logout(db: AsyncSession, user: User) -> None:
    """JWT không lưu phía server: client tự xóa token. Ở đây chỉ ghi nhật ký."""
    log_activity(db, user_id=user.user_id, action="LOGOUT", entity_type="user", entity_id=user.user_id)
    await db.commit()


async def update_profile(db: AsyncSession, user: User, data: UpdateProfileRequest) -> User:
    changes = data.model_dump(exclude_unset=True)
    if "email" in changes and changes["email"] is not None:
        changes["email"] = changes["email"].lower()
        await ensure_unique_account(db, email=changes["email"], exclude_user_id=user.user_id)
    for field, new_value in changes.items():
        if new_value is None and field != "phone":
            continue
        old_value = getattr(user, field)
        if old_value != new_value:
            setattr(user, field, new_value)
            log_activity(
                db,
                user_id=user.user_id,
                action="UPDATE_PROFILE",
                entity_type="user",
                entity_id=user.user_id,
                field_name=field,
                old_value=old_value,
                new_value=new_value,
            )
    await db.commit()
    await db.refresh(user)
    return user


async def change_password(db: AsyncSession, user: User, data: ChangePasswordRequest) -> None:
    if not verify_password(data.current_password, user.password_hash):
        raise UnauthorizedError("Mật khẩu hiện tại không đúng", code="WRONG_PASSWORD")
    user.password_hash = hash_password(data.new_password)
    # Không ghi mật khẩu vào nhật ký (NFR-04)
    log_activity(db, user_id=user.user_id, action="CHANGE_PASSWORD", entity_type="user", entity_id=user.user_id)
    await db.commit()
