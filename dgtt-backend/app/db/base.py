from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Lớp cha của mọi model ORM.

    Lưu ý: bảng KHÔNG được tạo từ model. Nguồn chuẩn của schema là
    `sql/dgtt_schema_postgresql.sql` (chạy qua migration 0001). Model chỉ ánh xạ lại.
    """
