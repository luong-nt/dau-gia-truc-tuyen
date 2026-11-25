"""Điểm khởi động ứng dụng FastAPI.

Chạy:  uvicorn app.main:app --reload
Tài liệu API: http://localhost:8000/docs
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.deps import REFRESHED_TOKEN_HEADER
from app.core.exceptions import register_exception_handlers
from app.core.scheduler import shutdown_scheduler, start_scheduler
from app.db.session import engine
from app.modules.assets.router import router as assets_router
from app.modules.auth.router import router as auth_router
from app.modules.bidding.router import router as bidding_router
from app.modules.bidding.ws import router as bidding_ws_router
from app.modules.registrations.router import router as registrations_router
from app.modules.reports.router import router as reports_router
from app.modules.results.router import router as results_router
from app.modules.sessions.router import router as sessions_router
from app.modules.users.router import router as users_router

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    if settings.scheduler_enabled:
        start_scheduler()
    yield
    shutdown_scheduler()
    await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="DGTT - Hệ thống quản lý đấu giá trực tuyến",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[REFRESHED_TOKEN_HEADER],
    )
    register_exception_handlers(app)

    for router in (
        auth_router,
        users_router,
        assets_router,
        sessions_router,
        registrations_router,
        bidding_router,
        results_router,
        reports_router,
    ):
        app.include_router(router, prefix=API_PREFIX)
    app.include_router(bidding_ws_router)

    @app.get("/health", tags=["Hệ thống"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
