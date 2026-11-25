"""Tạo schema ban đầu từ file SQL chuẩn sql/dgtt_schema_postgresql.sql

Revision ID: 0001
Revises:
Create Date: 2026-11-25
"""

from collections.abc import Sequence
from pathlib import Path

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SQL_FILE = Path(__file__).resolve().parents[2] / "sql" / "dgtt_schema_postgresql.sql"

TABLES_IN_DROP_ORDER = [
    "auction_results",
    "attachments",
    "bids",
    "registration_reviews",
    "registrations",
    "auction_sessions",
    "assets",
    "asset_owners",
    "activity_logs",
    "users",
]


def _statements(sql: str) -> list[str]:
    """Tách file SQL thành từng câu lệnh (asyncpg không chạy nhiều lệnh trong một lần)."""
    lines = [line for line in sql.splitlines() if not line.strip().startswith("--")]
    return [stmt.strip() for stmt in "\n".join(lines).split(";") if stmt.strip()]


def upgrade() -> None:
    bind = op.get_bind()
    for statement in _statements(SQL_FILE.read_text(encoding="utf-8")):
        bind.exec_driver_sql(statement)


def downgrade() -> None:
    bind = op.get_bind()
    for table in TABLES_IN_DROP_ORDER:
        bind.exec_driver_sql(f"DROP TABLE IF EXISTS {table} CASCADE")
