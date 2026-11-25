from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Response, UploadFile, status
from fastapi.responses import FileResponse

from app.core.deps import REFRESHED_TOKEN_HEADER, DbSession, require_roles
from app.core.pagination import Page, Pagination
from app.db.enums import RegistrationStatus, UserRole
from app.db.models import User
from app.modules.registrations import service
from app.modules.registrations.schemas import (
    DecisionRequest,
    EligibleListOut,
    RegistrationDetailOut,
    RegistrationResubmitRequest,
    RegistrationSubmitRequest,
    ReviewCheckRequest,
    StaffReviewOut,
    registration_resubmit_form,
    registration_submit_form,
)

router = APIRouter(tags=["Hồ sơ đăng ký (FR-10 - FR-15)"])

BidderUser = Annotated[User, Depends(require_roles(UserRole.BIDDER))]
AttachmentUser = Annotated[User, Depends(require_roles(UserRole.BIDDER, UserRole.STAFF))]
StaffUser = Annotated[User, Depends(require_roles(UserRole.STAFF))]
EligibleUser = Annotated[User, Depends(require_roles(UserRole.STAFF, UserRole.AUCTIONEER))]


@router.post(
    "/sessions/{session_id}/registrations",
    response_model=RegistrationDetailOut,
    status_code=status.HTTP_201_CREATED,
)
async def submit_registration(
    session_id: int,
    bidder: BidderUser,
    db: DbSession,
    data: Annotated[RegistrationSubmitRequest, Depends(registration_submit_form)],
    identity_documents: Annotated[list[UploadFile] | None, File()] = None,
    deposit_receipt: Annotated[UploadFile | None, File()] = None,
) -> RegistrationDetailOut:
    return await service.submit_registration(db, session_id, bidder, data, identity_documents or [], deposit_receipt)


@router.get("/registrations/me", response_model=Page[RegistrationDetailOut])
async def list_my_registrations(
    bidder: BidderUser,
    db: DbSession,
    page: Pagination,
    status: RegistrationStatus | None = None,
) -> Page[RegistrationDetailOut]:
    return await service.list_my_registrations(db, bidder, status=status, page=page)


@router.get("/registrations/{registration_id}/attachments/{attachment_id}")
async def download_attachment(
    registration_id: int,
    attachment_id: int,
    user: AttachmentUser,
    db: DbSession,
    response: Response,
) -> FileResponse:
    path, filename = await service.get_attachment_download(db, registration_id, attachment_id, user)
    return FileResponse(
        path, filename=filename, headers={REFRESHED_TOKEN_HEADER: response.headers[REFRESHED_TOKEN_HEADER]}
    )


@router.get("/registrations", response_model=Page[RegistrationDetailOut])
async def list_registrations(
    staff: StaffUser,
    db: DbSession,
    page: Pagination,
    session_id: int | None = None,
    status: RegistrationStatus | None = None,
    keyword: str | None = None,
) -> Page[RegistrationDetailOut]:
    return await service.list_registrations(db, session_id=session_id, status=status, keyword=keyword, page=page)


@router.get("/registrations/{registration_id}", response_model=RegistrationDetailOut)
async def get_registration(registration_id: int, user: AttachmentUser, db: DbSession) -> RegistrationDetailOut:
    return await service.get_registration_detail(db, registration_id, user)


@router.post(
    "/registrations/{registration_id}/checks", response_model=StaffReviewOut, status_code=status.HTTP_201_CREATED
)
async def record_check(
    registration_id: int,
    data: ReviewCheckRequest,
    staff: StaffUser,
    db: DbSession,
) -> StaffReviewOut:
    return await service.record_check(db, registration_id, data, staff)


@router.post("/registrations/{registration_id}/decision", response_model=RegistrationDetailOut)
async def decide(
    registration_id: int,
    data: DecisionRequest,
    staff: StaffUser,
    db: DbSession,
) -> RegistrationDetailOut:
    return await service.decide(db, registration_id, data, staff)


@router.put("/registrations/{registration_id}", response_model=RegistrationDetailOut)
async def resubmit(
    registration_id: int,
    bidder: BidderUser,
    db: DbSession,
    data: Annotated[RegistrationResubmitRequest, Depends(registration_resubmit_form)],
    identity_documents: Annotated[list[UploadFile] | None, File()] = None,
    deposit_receipt: Annotated[UploadFile | None, File()] = None,
) -> RegistrationDetailOut:
    return await service.resubmit(db, registration_id, data, bidder, identity_documents or [], deposit_receipt)


@router.get("/sessions/{session_id}/eligible-bidders", response_model=EligibleListOut)
async def list_eligible_bidders(session_id: int, user: EligibleUser, db: DbSession) -> EligibleListOut:
    return await service.list_eligible_bidders(db, session_id, user)


@router.get("/sessions/{session_id}/eligible-bidders/export")
async def export_eligible_bidders(
    session_id: int,
    user: EligibleUser,
    db: DbSession,
    response: Response,
    format: Literal["csv", "pdf"],
    include_identity: bool = False,
) -> Response:
    content = await service.export_eligible_bidders(
        db, session_id, user, format=format, include_identity=include_identity
    )
    return Response(
        content=content,
        media_type="text/csv" if format == "csv" else "application/pdf",
        headers={
            REFRESHED_TOKEN_HEADER: response.headers[REFRESHED_TOKEN_HEADER],
            "Content-Disposition": f'attachment; filename="danh-sach-du-dieu-kien-PDG-{session_id}.{format}"',
        },
    )
