from fastapi import APIRouter

router = APIRouter(tags=["Thống kê, báo cáo, nhật ký (FR-24 - FR-26)"])

# TODO(FR-24): GET "/reports/summary?from=&to="     số tài sản, hồ sơ theo trạng thái, phiên theo kết quả
#              (tách phiên chờ xác nhận với phiên đã có kết quả CONFIRMED)
# TODO(FR-25): GET "/reports/results/export?from=&to=&format=csv|pdf"
#              chỉ cộng giá trúng của kết quả CONFIRMED; ghi thời điểm tạo và điều kiện lọc
# TODO(FR-26): GET "/activity-logs?user_id=&action=&entity_type=&from=&to="   chỉ ADMIN, chỉ đọc
