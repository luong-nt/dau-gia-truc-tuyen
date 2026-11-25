from fastapi import APIRouter, status

from app.core.deps import CurrentUser, DbSession
from app.modules.auth import service
from app.modules.auth.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UpdateProfileRequest,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["Tài khoản (FR-01 - FR-03)"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(data: RegisterRequest, db: DbSession):
    return await service.register_bidder(db, data)


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest, db: DbSession):
    return await service.login(db, data.login, data.password)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(user: CurrentUser, db: DbSession):
    await service.logout(db, user)


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser):
    return user


@router.put("/me", response_model=UserOut)
async def update_me(data: UpdateProfileRequest, user: CurrentUser, db: DbSession):
    return await service.update_profile(db, user, data)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(data: ChangePasswordRequest, user: CurrentUser, db: DbSession):
    await service.change_password(db, user, data)
