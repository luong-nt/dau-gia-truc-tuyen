"""Dependency dùng chung: phiên DB, người dùng hiện tại, kiểm tra vai trò (NFR-05)."""

from collections.abc import Awaitable, Callable
from typing import Annotated

import jwt
from fastapi import Depends, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import create_access_token, decode_access_token
from app.db.enums import UserRole, UserStatus
from app.db.models import User
from app.db.session import get_db

DbSession = Annotated[AsyncSession, Depends(get_db)]

_bearer = HTTPBearer(auto_error=False)

# Header chứa token mới sau mỗi request hợp lệ (gia hạn trượt 30 phút - NFR-04)
REFRESHED_TOKEN_HEADER = "X-Access-Token"


async def authenticate_token(db: AsyncSession, token: str) -> User:
    """Giải mã token và trả về người dùng đang hoạt động. Dùng chung cho HTTP và WebSocket."""
    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("Phiên đăng nhập đã hết hạn, vui lòng đăng nhập lại", code="TOKEN_EXPIRED") from exc
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("Token không hợp lệ") from exc

    user = await db.get(User, int(payload["sub"]))
    if user is None or user.status != UserStatus.ACTIVE:
        raise UnauthorizedError("Tài khoản không tồn tại hoặc đã bị khóa")
    return user


async def get_current_user(
    response: Response,
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    if credentials is None:
        raise UnauthorizedError("Bạn chưa đăng nhập")
    user = await authenticate_token(db, credentials.credentials)
    response.headers[REFRESHED_TOKEN_HEADER] = create_access_token(user.user_id, user.role)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: UserRole) -> Callable[[User], Awaitable[User]]:
    """Dùng: `user: Annotated[User, Depends(require_roles(UserRole.STAFF))]`."""

    async def checker(user: CurrentUser) -> User:
        if user.role not in roles:
            raise ForbiddenError("Bạn không có quyền thực hiện thao tác này")
        return user

    return checker


async def get_optional_user(
    response: Response,
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User | None:
    """Cho phép khách; token được cung cấp vẫn phải hợp lệ và được gia hạn."""
    if credentials is None:
        return None
    user = await authenticate_token(db, credentials.credentials)
    response.headers[REFRESHED_TOKEN_HEADER] = create_access_token(user.user_id, user.role)
    return user


OptionalUser = Annotated[User | None, Depends(get_optional_user)]
