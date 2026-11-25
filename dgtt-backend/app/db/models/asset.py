from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String, Text, false, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Asset(Base):
    __tablename__ = "assets"

    asset_id: Mapped[int] = mapped_column(primary_key=True)
    asset_code: Mapped[str] = mapped_column(String(30), unique=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("asset_owners.owner_id"))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), server_default="UPCOMING")
    is_public: Mapped[bool] = mapped_column(Boolean, server_default=false())
    created_by: Mapped[int] = mapped_column(ForeignKey("users.user_id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.current_timestamp())
