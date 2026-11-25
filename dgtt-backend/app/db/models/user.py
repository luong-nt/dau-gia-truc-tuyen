from datetime import datetime

from sqlalchemy import String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(primary_key=True)
    role: Mapped[str] = mapped_column(String(20))
    username: Mapped[str] = mapped_column(String(50), unique=True)
    email: Mapped[str] = mapped_column(String(100), unique=True)
    phone: Mapped[str | None] = mapped_column(String(15))
    full_name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), server_default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(server_default=func.current_timestamp())
