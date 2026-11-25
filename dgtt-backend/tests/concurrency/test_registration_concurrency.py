"""Tranh chấp đồng thời trong luồng hồ sơ.

- TASK-001 Quy tắc 5: nhiều request nộp hồ sơ đồng thời của cùng một người cho cùng phiên. Chỉ một request thành
  công (201), các request còn lại nhận 409 ALREADY_REGISTERED (không 500); DB chỉ có một hồ sơ, một bộ tệp.
- TASK-002 AC-13: duyệt đồng thời nhiều hồ sơ của cùng một phiên. Mã bidder_alias NTG-01... không trùng, không 500.
"""

import asyncio

import pytest
from sqlalchemy import func, select

from app.db.enums import RegistrationStatus, ReviewResult, ReviewType
from app.db.models import ActivityLog, Attachment, Registration
from app.db.session import SessionLocal
from tests.factories import add_review, create_registration, create_registration_scenario, login_headers

pytestmark = pytest.mark.db

N = 5
PDF_BYTES = b"%PDF-1.4\n% tai lieu test\n%%EOF\n"


async def test_concurrent_duplicate_submit(client, db, prefix):
    """TASK-001 Quy tắc 5: nộp đồng thời cùng người cùng phiên -> đúng 1 lần 201, còn lại 409 ALREADY_REGISTERED"""
    sc = await create_registration_scenario(db, prefix=prefix)
    sid = sc.session.session_id
    bidder = sc.users["bidder1"]
    h = await login_headers(client, bidder.username)

    async def submit(i: int):
        return await client.post(
            f"/api/v1/sessions/{sid}/registrations",
            data={"submitted_full_name": f"Nguyễn Văn {i}", "submitted_id_number": "001090012345"},
            files=[("identity_documents", (f"cccd{i}.pdf", PDF_BYTES, "application/pdf"))],
            headers=h,
        )

    responses = await asyncio.gather(*(submit(i) for i in range(N)))

    statuses = sorted(r.status_code for r in responses)
    assert statuses == [201] + [409] * (N - 1), [r.text for r in responses]
    for r in responses:
        if r.status_code == 409:
            assert r.json()["code"] == "ALREADY_REGISTERED"

    winner = next(r.json() for r in responses if r.status_code == 201)
    winner_id = winner["registration_id"]
    async with SessionLocal() as s:
        reg_query = select(Registration.registration_id).where(
            Registration.session_id == sid, Registration.bidder_id == bidder.user_id
        )
        assert list(await s.scalars(reg_query)) == [winner_id]

        # Chỉ có tệp của lần nộp thành công
        att_query = select(Attachment.file_name).where(Attachment.registration_id == winner_id)
        assert list(await s.scalars(att_query)) == [winner["attachments"][0]["file_name"]]

        log_query = select(func.count()).where(
            ActivityLog.action == "SUBMIT_REGISTRATION", ActivityLog.user_id == bidder.user_id
        )
        assert await s.scalar(log_query) == 1


APPROVE_N = 10


async def test_concurrent_approvals_unique_aliases(client, db, prefix):
    """TASK-002 AC-13: duyệt đồng thời 10 hồ sơ cùng phiên -> 10 lần 200, mã NTG-01..NTG-10 không trùng"""
    sc = await create_registration_scenario(db, prefix=prefix, bidder_count=APPROVE_N)
    sid = sc.session.session_id
    staff = sc.users["staff"]
    registration_ids = []
    for i in range(1, APPROVE_N + 1):
        reg = await create_registration(db, session_id=sid, bidder=sc.users[f"bidder{i}"])
        for review_type in (ReviewType.DOCUMENT_CHECK, ReviewType.ELIGIBILITY_CHECK, ReviewType.DEPOSIT_CHECK):
            await add_review(
                db,
                registration_id=reg.registration_id,
                review_type=review_type,
                result=ReviewResult.PASSED,
                reviewed_by=staff.user_id,
            )
        registration_ids.append(reg.registration_id)
    h = await login_headers(client, staff.username)

    async def approve(registration_id: int):
        return await client.post(
            f"/api/v1/registrations/{registration_id}/decision", json={"decision": "APPROVE"}, headers=h
        )

    responses = await asyncio.gather(*(approve(rid) for rid in registration_ids))

    assert [r.status_code for r in responses] == [200] * APPROVE_N, [r.text for r in responses]
    expected = {f"NTG-{i:02d}" for i in range(1, APPROVE_N + 1)}
    assert {r.json()["bidder_alias"] for r in responses} == expected

    async with SessionLocal() as s:
        rows = (
            await s.execute(
                select(Registration.status, Registration.bidder_alias).where(Registration.session_id == sid)
            )
        ).all()
        assert len(rows) == APPROVE_N
        assert {status for status, _ in rows} == {RegistrationStatus.APPROVED}
        assert {alias for _, alias in rows} == expected

        log_query = select(func.count()).where(
            ActivityLog.action == "APPROVE_REGISTRATION", ActivityLog.entity_id.in_(registration_ids)
        )
        assert await s.scalar(log_query) == APPROVE_N
