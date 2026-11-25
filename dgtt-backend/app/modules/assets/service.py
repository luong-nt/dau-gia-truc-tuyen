"""Nghiệp vụ tài sản (FR-05 - FR-07).

Trạng thái tài sản (quy ước đã thống nhất):
    tạo mới                        -> UPCOMING
    phiên chuyển IN_PROGRESS       -> IN_AUCTION   (module sessions tự cập nhật)
    kết quả CONFIRMED có người trúng -> ENDED      (module results)
    không thành / phiên bị hủy     -> UPCOMING     (để tổ chức lại)
    Nhân viên chủ động             -> SUSPENDED_CANCELLED
"""

# TODO(FR-05): create_asset, update_asset (log_activity cho từng trường thay đổi khi is_public)
# TODO(FR-06): delete_asset (chỉ khi chưa có phiên), suspend_asset
# TODO(FR-05): add_attachment(asset_id, UploadFile, file_type) dùng core.storage.save_upload
