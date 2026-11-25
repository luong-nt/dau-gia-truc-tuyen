from fastapi import APIRouter

router = APIRouter(tags=["Tài sản đấu giá (FR-05 - FR-07)"])

# Người có tài sản (Nhân viên)
# TODO(FR-05): GET   "/asset-owners"                    tìm kiếm người có tài sản
# TODO(FR-05): POST  "/asset-owners"                    thêm người có tài sản (id_number duy nhất)
# TODO(FR-05): PUT   "/asset-owners/{owner_id}"

# Tài sản
# TODO(FR-07): GET   "/assets"                          tra cứu: tên/mã, trạng thái; Khách chỉ thấy is_public
# TODO(FR-07): GET   "/assets/{asset_id}"               chi tiết + ảnh + phiên liên quan
# TODO(FR-05): POST  "/assets"                          Nhân viên thêm tài sản (asset_code duy nhất)
# TODO(FR-05): PUT   "/assets/{asset_id}"               đã công khai thì ghi activity_logs kèm lý do
# TODO(FR-06): DELETE "/assets/{asset_id}"              chỉ xóa khi chưa gắn phiên/hồ sơ
# TODO(FR-06): PATCH "/assets/{asset_id}/status"        đặt SUSPENDED_CANCELLED (có lý do)
# TODO(FR-05): POST  "/assets/{asset_id}/attachments"   upload ảnh JPG/PNG, tài liệu (core.storage)
# TODO(FR-07): GET   "/assets/{asset_id}/attachments/{attachment_id}"  tải tệp (kiểm tra quyền)
