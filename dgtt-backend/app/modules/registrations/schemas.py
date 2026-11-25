from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import Form
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.db.enums import FileType, RegistrationStatus, ReviewResult, ReviewType

SubmittedName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
SubmittedIdNumber = Annotated[str, StringConstraints(min_length=9, max_length=20, pattern=r"^[0-9]+$")]
SubmittedAddress = Annotated[str, StringConstraints(max_length=255)]
SubmittedPhone = Annotated[str, StringConstraints(pattern=r"^[0-9+]{9,15}$")]


class RegistrationSubmitRequest(BaseModel):
    """Bản thông tin người tham gia nộp cho một phiên."""

    submitted_full_name: SubmittedName
    submitted_id_number: SubmittedIdNumber
    submitted_address: SubmittedAddress | None = None
    submitted_phone: SubmittedPhone | None = None


def registration_submit_form(
    submitted_full_name: Annotated[SubmittedName, Form()],
    submitted_id_number: Annotated[SubmittedIdNumber, Form()],
    submitted_address: Annotated[SubmittedAddress | None, Form()] = None,
    submitted_phone: Annotated[SubmittedPhone | None, Form()] = None,
) -> RegistrationSubmitRequest:
    """Kiểm tra trường văn bản multipart trước khi chuyển vào service."""
    return RegistrationSubmitRequest(
        submitted_full_name=submitted_full_name,
        submitted_id_number=submitted_id_number,
        submitted_address=submitted_address,
        submitted_phone=submitted_phone,
    )


class RegistrationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    registration_id: int
    session_id: int
    bidder_id: int
    submitted_full_name: str
    submitted_id_number: str
    submitted_address: str | None
    submitted_phone: str | None
    submission_count: int
    status: str
    supplement_deadline: datetime | None
    bidder_alias: str | None
    submitted_at: datetime


class AttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    attachment_id: int
    file_type: FileType
    file_name: str
    file_format: str | None
    file_size: int | None
    submission_no: int | None
    uploaded_at: datetime


class ReviewOut(BaseModel):
    """Phản hồi cho chủ hồ sơ, ẩn người kiểm tra và căn cứ nội bộ."""

    model_config = ConfigDict(from_attributes=True)

    review_type: ReviewType
    result: ReviewResult | None
    reason: str | None
    reviewed_at: datetime


class StaffReviewOut(ReviewOut):
    review_id: int
    registration_id: int
    reviewed_by: int
    evidence: str | None


class RegistrationDetailOut(BaseModel):
    registration_id: int
    session_id: int
    session_code: str
    submitted_full_name: str
    submitted_id_number: str
    submitted_address: str | None
    submitted_phone: str | None
    submission_count: int
    status: RegistrationStatus
    supplement_deadline: datetime | None
    bidder_alias: str | None
    submitted_at: datetime
    attachments: list[AttachmentOut]
    reviews: list[StaffReviewOut | ReviewOut]


class EligibleBidderOut(BaseModel):
    registration_id: int
    bidder_alias: str
    full_name: str
    approved_at: datetime | None


class EligibleListOut(BaseModel):
    session_id: int
    session_code: str
    asset_name: str
    total: int
    items: list[EligibleBidderOut]


class ReviewCheckRequest(BaseModel):
    review_type: Literal[ReviewType.DOCUMENT_CHECK, ReviewType.ELIGIBILITY_CHECK, ReviewType.DEPOSIT_CHECK]
    result: ReviewResult
    reason: str | None = Field(default=None, max_length=500)
    evidence: str | None = Field(default=None, max_length=500)


class DecisionRequest(BaseModel):
    decision: Literal[ReviewType.APPROVE, ReviewType.REQUEST_SUPPLEMENT, ReviewType.REJECT]
    reason: str | None = Field(default=None, max_length=500)
    supplement_deadline: datetime | None = None

    @field_validator("supplement_deadline")
    @classmethod
    def normalize_utc(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is not None:
            return value.astimezone(UTC).replace(tzinfo=None)
        return value


class RegistrationResubmitRequest(BaseModel):
    submitted_full_name: SubmittedName | None = None
    submitted_id_number: SubmittedIdNumber | None = None
    submitted_address: SubmittedAddress | None = None
    submitted_phone: SubmittedPhone | None = None


def registration_resubmit_form(
    submitted_full_name: Annotated[SubmittedName | None, Form()] = None,
    submitted_id_number: Annotated[SubmittedIdNumber | None, Form()] = None,
    submitted_address: Annotated[SubmittedAddress | None, Form()] = None,
    submitted_phone: Annotated[SubmittedPhone | None, Form()] = None,
) -> RegistrationResubmitRequest:
    """Chỉ giữ các trường text được gửi để nộp bổ sung."""
    values = dict(
        submitted_full_name=submitted_full_name,
        submitted_id_number=submitted_id_number,
        submitted_address=submitted_address,
        submitted_phone=submitted_phone,
    )
    return RegistrationResubmitRequest(**{key: value for key, value in values.items() if value is not None})
