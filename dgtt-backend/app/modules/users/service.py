"""Quản lý tài khoản và phân quyền (FR-04). Mọi thay đổi quyền đều ghi nhật ký."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_activity
from app.core.exceptions import BusinessRuleError, NotFoundError
from app.core.pagination import Page, PageParams
from app.core.security import hash_password
from app.db.enums import UserStatus
from app.db.models import User
from app.modules.auth.schemas import UserOut
from app.modules.auth.service import ensure_unique_account
from app.modules.users import repository
from app.modules.users.schemas import ChangeRoleRequest, ChangeStatusRequest, CreateUserRequest


async def list_users(
    db: AsyncSession,
    *,
    keyword: str | None,
    role: str | None,
    status: str | None,
    page: PageParams,
) -> Page[UserOut]:
    users, total = await repository.search_users(
        db, keyword=keyword, role=role, status=status, offset=page.offset, limit=page.size
    )
    return Page[UserOut](
        items=[UserOut.model_validate(u) for u in users],
        total=total,
        page=page.page,
        size=page.size,
    )


async def create_user(db: AsyncSession, admin: User, data: CreateUserRequest) -> User:
    await ensure_unique_account(db, username=data.username, email=data.email)
    user = User(
        role=data.role,
        username=data.username,
        email=data.email.lower(),
        phone=data.phone,
        full_name=data.full_name.strip(),
        password_hash=hash_password(data.password),
        status=UserStatus.ACTIVE,
    )
    db.add(user)
    await db.flush()
    log_activity(
        db,
        user_id=admin.user_id,
        action="CREATE_USER",
        entity_type="user",
        entity_id=user.user_id,
        field_name="role",
        new_value=user.role,
    )
    await db.commit()
    await db.refresh(user)
    return user


async def _get_user(db: AsyncSession, user_id: int) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise NotFoundError("Không tìm thấy tài khoản")
    return user


async def change_role(db: AsyncSession, admin: User, user_id: int, data: ChangeRoleRequest) -> User:
    user = await _get_user(db, user_id)
    if user.user_id == admin.user_id:
        raise BusinessRuleError("Không thể tự đổi vai trò của chính mình")
    old_role = user.role
    if old_role != data.role:
        user.role = data.role
        log_activity(
            db,
            user_id=admin.user_id,
            action="CHANGE_ROLE",
            entity_type="user",
            entity_id=user.user_id,
            field_name="role",
            old_value=old_role,
            new_value=data.role,
            reason=data.reason,
        )
        await db.commit()
        await db.refresh(user)
    return user


async def change_status(db: AsyncSession, admin: User, user_id: int, data: ChangeStatusRequest) -> User:
    user = await _get_user(db, user_id)
    if user.user_id == admin.user_id:
        raise BusinessRuleError("Không thể tự khóa tài khoản của chính mình")
    old_status = user.status
    if old_status != data.status:
        user.status = data.status
        action = "LOCK_USER" if data.status == UserStatus.LOCKED else "UNLOCK_USER"
        log_activity(
            db,
            user_id=admin.user_id,
            action=action,
            entity_type="user",
            entity_id=user.user_id,
            field_name="status",
            old_value=old_status,
            new_value=data.status,
            reason=data.reason,
        )
        await db.commit()
        await db.refresh(user)
    return user
