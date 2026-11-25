from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    asset_id: int
    asset_code: str
    owner_id: int
    name: str
    description: str | None
    status: str
    is_public: bool
    created_at: datetime


# TODO(FR-05): AssetCreateRequest, AssetUpdateRequest, AssetOwnerCreateRequest, AssetOwnerOut
# Lưu ý: giá khởi điểm, bước giá KHÔNG thuộc tài sản mà thuộc từng phiên (auction_sessions).
