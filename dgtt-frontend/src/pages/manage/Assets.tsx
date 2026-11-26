// SCR-07 – Quản lý tài sản (FR-05, FR-06)
// Backend chưa có API tài sản (TASK-007, TASK-008 trong docs/TASKS.md của dgtt-backend).
// Khi có API, làm theo thiết kế SCR-07 (Mục 4.7.4.7) và prototype dgtt-frontend-prototype/screens/scr07-quan-ly-tai-san.html.
export default function Assets() {
  return (
    <div className="card col" style={{ maxWidth: 720 }}>
      <div className="h1">Quản lý tài sản</div>
      <div className="warn">
        Chức năng đang chờ backend hoàn thành API tài sản (TASK-007: thêm/sửa/xóa/tra cứu; TASK-008: tải ảnh và tài liệu).
      </div>
      <div className="mut" style={{ fontSize: 13, lineHeight: 1.7 }}>
        Khi API sẵn sàng, màn hình sẽ gồm: bảng tài sản có bộ lọc theo trạng thái (Sắp đấu giá, Đang đấu giá, Đã kết thúc,
        Tạm dừng/Hủy), biểu mẫu thêm/sửa với ảnh JPG/PNG, và bắt buộc nhập lý do khi sửa tài sản đã gắn phiên công khai.
        Hiện tại, khi tạo phiên đấu giá hãy nhập mã số tài sản (ID).
      </div>
    </div>
  );
}
