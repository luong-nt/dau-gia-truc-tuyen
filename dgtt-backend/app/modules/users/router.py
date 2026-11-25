from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.deps import DbSession, require_roles
from app.core.pagination import Page, Pagination
from app.db.enums import UserRole, UserStatus
from app.db.models import User
from app.modules.auth.schemas import UserOut
from app.modules.users import service
from app.modules.users.schemas import ChangeRoleRequest, ChangeStatusRequest, CreateUserRequest

router = APIRouter(prefix="/users", tags=["Quản lý tài khoản (FR-04)"])

AdminUser = Annotated[User, Depends(require_roles(UserRole.ADMIN))]


@router.get("", response_model=Page[UserOut])
async def list_users(
    admin: AdminUser,
    db: DbSession,
    page: Pagination,
    keyword: Annotated[str | None, Query(max_length=100)] = None,
    role: UserRole | None = None,
    user_status: Annotated[UserStatus | None, Query(alias="status")] = None,
):
    return await service.list_users(db, keyword=keyword, role=role, status=user_status, page=page)


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(data: CreateUserRequest, admin: AdminUser, db: DbSession):
    return await service.create_user(db, admin, data)


@router.patch("/{user_id}/role", response_model=UserOut)
async def change_role(user_id: int, data: ChangeRoleRequest, admin: AdminUser, db: DbSession):
    return await service.change_role(db, admin, user_id, data)


@router.patch("/{user_id}/status", response_model=UserOut)
async def change_status(user_id: int, data: ChangeStatusRequest, admin: AdminUser, db: DbSession):
    return await service.change_status(db, admin, user_id, data)
