"""Hai kịch bản nghiệm thu TC-REV-002 và TC-RES-003 trên API và database thật.

Dữ liệu đầu vào được tạo riêng cho từng test. Không giả lập phản hồi API hay bộ xuất PDF;
TC-RES-003 phải thất bại nếu hệ thống chưa xuất được biên bản.
"""

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db.enums import AssetStatus, RegistrationStatus, ResultStatus, ReviewResult, ReviewType
from app.db.models import ActivityLog, Asset, AuctionResult, Registration, RegistrationReview
from app.db.session import SessionLocal
from tests.factories import (
    create_registration,
    create_registration_scenario,
    create_result_scenario,
    login_headers,
)

pytestmark = pytest.mark.db


async def test_tc_rev_002_review_registration_and_confirm_deposit(client, db, prefix):
    """TC-REV-002 – Xét duyệt hồ sơ, bước xác nhận tiền đặt trước.

    Chỉ cho duyệt sau khi giấy tờ, điều kiện và xác nhận tiền mới nhất đều đạt;
    lưu căn cứ đối chiếu, người xác nhận, lịch sử kiểm tra và nhật ký.
    """
    scenario = await create_registration_scenario(db, prefix=prefix, bidder_count=1)
    staff = scenario.users["staff"]
    registration = await create_registration(
        db, session_id=scenario.session.session_id, bidder=scenario.users["bidder1"]
    )
    url = f"/api/v1/registrations/{registration.registration_id}"
    headers = await login_headers(client, staff.username)

    for review_type in (ReviewType.DOCUMENT_CHECK, ReviewType.ELIGIBILITY_CHECK):
        response = await client.post(
            f"{url}/checks", headers=headers, json={"review_type": review_type, "result": ReviewResult.PASSED}
        )
        assert response.status_code == 201, response.text

    # Giấy tờ và điều kiện đã đạt vẫn chưa đủ để duyệt nếu chưa xác nhận tiền.
    response = await client.post(f"{url}/decision", headers=headers, json={"decision": "APPROVE"})
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "CHECKS_NOT_PASSED"

    response = await client.post(
        f"{url}/checks",
        headers=headers,
        json={
            "review_type": ReviewType.DEPOSIT_CHECK,
            "result": ReviewResult.FAILED,
            "reason": "Chưa ghi nhận đủ tiền đặt trước",
            "evidence": "Đối soát lần 1: chưa có giao dịch ghi có",
        },
    )
    assert response.status_code == 201, response.text
    response = await client.post(f"{url}/decision", headers=headers, json={"decision": "APPROVE"})
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "CHECKS_NOT_PASSED"

    evidence = "UNC-TC-REV-002: đã đối soát đủ tiền đặt trước"
    response = await client.post(
        f"{url}/checks",
        headers=headers,
        json={"review_type": ReviewType.DEPOSIT_CHECK, "result": ReviewResult.PASSED, "evidence": evidence},
    )
    assert response.status_code == 201, response.text
    assert response.json()["reviewed_by"] == staff.user_id
    assert response.json()["reviewed_at"]
    assert response.json()["evidence"] == evidence

    response = await client.post(f"{url}/decision", headers=headers, json={"decision": "APPROVE"})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == RegistrationStatus.APPROVED
    assert response.json()["bidder_alias"] == "NTG-01"

    async with SessionLocal() as session:
        saved = await session.get(Registration, registration.registration_id)
        assert saved.status == RegistrationStatus.APPROVED
        assert saved.bidder_alias == "NTG-01"
        checks = list(
            await session.scalars(
                select(RegistrationReview)
                .where(
                    RegistrationReview.registration_id == registration.registration_id,
                    RegistrationReview.review_type == ReviewType.DEPOSIT_CHECK,
                )
                .order_by(RegistrationReview.review_id)
            )
        )
        assert [check.result for check in checks] == [ReviewResult.FAILED, ReviewResult.PASSED]
        assert all(check.reviewed_by == staff.user_id and check.reviewed_at is not None for check in checks)
        assert checks[-1].evidence == evidence
        logs = list(
            await session.scalars(
                select(ActivityLog)
                .where(
                    ActivityLog.entity_type == "registration",
                    ActivityLog.entity_id == registration.registration_id,
                    ActivityLog.action.in_(("CONFIRM_DEPOSIT", "APPROVE_REGISTRATION")),
                )
                .order_by(ActivityLog.log_id)
            )
        )
        assert [log.action for log in logs] == ["CONFIRM_DEPOSIT", "CONFIRM_DEPOSIT", "APPROVE_REGISTRATION"]
        assert all(log.user_id == staff.user_id for log in logs)


async def test_tc_res_003_confirm_result_and_export_minutes(client, db, prefix):
    """TC-RES-003 – Đấu giá viên xác nhận kết quả và xuất biên bản.

    Đấu giá viên phụ trách xác nhận bản dự thảo, tài sản chuyển ENDED,
    sau đó tải biên bản PDF thật của đúng phiên bản đã xác nhận.
    """
    scenario = await create_result_scenario(db, prefix=prefix)
    auctioneer = scenario.users["auctioneer"]
    result_id = scenario.draft.result_id
    url = f"/api/v1/sessions/{scenario.session.session_id}/results"
    headers = await login_headers(client, auctioneer.username)

    response = await client.get(url, headers=headers)
    assert response.status_code == 200, response.text
    draft = next(result for result in response.json() if result["result_id"] == result_id)
    assert draft["status"] == ResultStatus.DRAFT
    assert draft["winning_bidder_alias"] == "NTG-02"
    assert Decimal(draft["winning_amount"]) == Decimal("105000000")

    response = await client.post(f"{url}/{result_id}/confirm", headers=headers, json={})
    assert response.status_code == 200, response.text
    confirmed = response.json()
    assert confirmed["status"] == ResultStatus.CONFIRMED
    assert confirmed["confirmed_by"] == auctioneer.user_id
    assert confirmed["confirmed_at"]

    async with SessionLocal() as session:
        saved = await session.get(AuctionResult, result_id)
        assert saved.status == ResultStatus.CONFIRMED
        assert saved.confirmed_by == auctioneer.user_id
        assert (await session.get(Asset, scenario.asset.asset_id)).status == AssetStatus.ENDED
        logs = list(
            await session.scalars(
                select(ActivityLog).where(
                    ActivityLog.entity_type == "auction_result",
                    ActivityLog.entity_id == result_id,
                    ActivityLog.action == "CONFIRM_RESULT",
                )
            )
        )
        assert len(logs) == 1
        assert logs[0].user_id == auctioneer.user_id

    response = await client.get(f"{url}/{result_id}/minutes", headers=headers)
    assert response.status_code == 200, (
        "TC-RES-003: xác nhận kết quả đã thành công nhưng tải biên bản PDF chưa đạt; "
        f"mong đợi HTTP 200, nhận HTTP {response.status_code}: {response.text}"
    )
    assert response.headers.get("content-type", "").startswith("application/pdf")
    assert "attachment" in response.headers.get("content-disposition", "").lower()
    assert response.content.startswith(b"%PDF-"), "Biên bản tải về phải là tệp PDF"
