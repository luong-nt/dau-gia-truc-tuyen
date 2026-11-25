"""Các giá trị liệt kê, khớp ĐÚNG với ràng buộc CHECK trong file SQL.

Dùng StrEnum nên so sánh trực tiếp được với chuỗi lưu trong DB:
    session.status == SessionStatus.IN_PROGRESS
"""

from enum import StrEnum


class UserRole(StrEnum):
    ADMIN = "ADMIN"
    STAFF = "STAFF"
    AUCTIONEER = "AUCTIONEER"
    BIDDER = "BIDDER"


class UserStatus(StrEnum):
    ACTIVE = "ACTIVE"
    LOCKED = "LOCKED"


class OwnerType(StrEnum):
    INDIVIDUAL = "INDIVIDUAL"
    ORGANIZATION = "ORGANIZATION"


class AssetStatus(StrEnum):
    UPCOMING = "UPCOMING"
    IN_AUCTION = "IN_AUCTION"
    ENDED = "ENDED"
    SUSPENDED_CANCELLED = "SUSPENDED_CANCELLED"


class SessionStatus(StrEnum):
    DRAFT = "DRAFT"
    OPEN_FOR_REGISTRATION = "OPEN_FOR_REGISTRATION"
    UPCOMING = "UPCOMING"
    IN_PROGRESS = "IN_PROGRESS"
    PAUSED = "PAUSED"
    ENDED = "ENDED"
    CANCELLED = "CANCELLED"


class RegistrationStatus(StrEnum):
    PENDING = "PENDING"
    NEEDS_SUPPLEMENT = "NEEDS_SUPPLEMENT"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ReviewType(StrEnum):
    DOCUMENT_CHECK = "DOCUMENT_CHECK"
    ELIGIBILITY_CHECK = "ELIGIBILITY_CHECK"
    DEPOSIT_CHECK = "DEPOSIT_CHECK"
    APPROVE = "APPROVE"
    REQUEST_SUPPLEMENT = "REQUEST_SUPPLEMENT"
    REJECT = "REJECT"


class ReviewResult(StrEnum):
    PASSED = "PASSED"
    FAILED = "FAILED"


class BidResult(StrEnum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class ResultStatus(StrEnum):
    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"
    SUPERSEDED = "SUPERSEDED"


class FileType(StrEnum):
    ASSET_IMAGE = "ASSET_IMAGE"
    ASSET_DOCUMENT = "ASSET_DOCUMENT"
    IDENTITY_DOCUMENT = "IDENTITY_DOCUMENT"
    DEPOSIT_RECEIPT = "DEPOSIT_RECEIPT"
    OTHER = "OTHER"
