"""Import mọi model để SQLAlchemy/Alembic biết đủ 10 bảng."""

from app.db.models.activity_log import ActivityLog
from app.db.models.asset import Asset
from app.db.models.asset_owner import AssetOwner
from app.db.models.attachment import Attachment
from app.db.models.auction_result import AuctionResult
from app.db.models.auction_session import AuctionSession
from app.db.models.bid import Bid
from app.db.models.registration import Registration
from app.db.models.registration_review import RegistrationReview
from app.db.models.user import User

__all__ = [
    "ActivityLog",
    "Asset",
    "AssetOwner",
    "Attachment",
    "AuctionResult",
    "AuctionSession",
    "Bid",
    "Registration",
    "RegistrationReview",
    "User",
]
