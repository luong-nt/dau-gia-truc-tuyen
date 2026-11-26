import type { Money, RegistrationStatus, Role, SessionStatus } from './api/types';

/** Đọc tiền từ backend (chuỗi Decimal, có thể ở dạng số mũ "1E+8"). */
export function money(v: Money | null | undefined): number {
  if (v === null || v === undefined || v === '') return 0;
  return typeof v === 'number' ? v : Number(v);
}

/** 412000000 -> "412.000.000 đ" (UI-09). */
export function vnd(v: Money | null | undefined): string {
  if (v === null || v === undefined) return '—';
  return Math.round(money(v)).toLocaleString('vi-VN') + ' đ';
}

/** Thời gian từ backend là UTC không kèm múi giờ -> thêm 'Z' để trình duyệt hiểu đúng. */
export function parseUtc(s: string | null | undefined): Date | null {
  if (!s) return null;
  return new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(s) ? s : s + 'Z');
}

const TZ = 'Asia/Ho_Chi_Minh';

/** "HH:mm dd/MM/yyyy" theo GMT+7. */
export function dt(s: string | null | undefined): string {
  const d = parseUtc(s);
  if (!d) return '—';
  const t = d.toLocaleTimeString('vi-VN', { timeZone: TZ, hour: '2-digit', minute: '2-digit', hour12: false });
  const day = d.toLocaleDateString('vi-VN', { timeZone: TZ, day: '2-digit', month: '2-digit', year: 'numeric' });
  return `${t} ${day}`;
}

export function timeOnly(s: string | null | undefined): string {
  const d = parseUtc(s);
  if (!d) return '—';
  return d.toLocaleTimeString('vi-VN', { timeZone: TZ, hour12: false });
}

/** Giá trị cho <input type="datetime-local"> theo giờ GMT+7. */
export function toLocalInput(s: string | null | undefined): string {
  const d = parseUtc(s);
  if (!d) return '';
  const shifted = new Date(d.getTime() + 7 * 3600_000);
  return shifted.toISOString().slice(0, 16);
}

/** Từ <input type="datetime-local"> (hiểu là GMT+7) -> ISO có múi giờ để gửi backend. */
export function fromLocalInput(v: string): string {
  return `${v}:00+07:00`;
}

export function countdown(ms: number): string {
  if (ms <= 0) return '00:00';
  const s = Math.floor(ms / 1000);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const pad = (n: number) => String(n).padStart(2, '0');
  return h > 0 ? `${h}:${pad(m)}:${pad(sec)}` : `${pad(m)}:${pad(sec)}`;
}

type Badge = { label: string; color: 'blue' | 'green' | 'amber' | 'red' | 'gray' | 'purple' };

// Bảng 4.7.2 – Quy ước nhãn trạng thái, khớp enums backend
export const SESSION_STATUS: Record<SessionStatus, Badge> = {
  DRAFT: { label: 'Nháp', color: 'gray' },
  OPEN_FOR_REGISTRATION: { label: 'Đang nhận hồ sơ', color: 'blue' },
  UPCOMING: { label: 'Sắp diễn ra', color: 'amber' },
  IN_PROGRESS: { label: 'Đang diễn ra', color: 'green' },
  PAUSED: { label: 'Tạm dừng', color: 'amber' },
  ENDED: { label: 'Đã kết thúc', color: 'gray' },
  CANCELLED: { label: 'Đã hủy', color: 'red' },
};

export const REG_STATUS: Record<RegistrationStatus, Badge> = {
  PENDING: { label: 'Chờ duyệt', color: 'amber' },
  NEEDS_SUPPLEMENT: { label: 'Yêu cầu bổ sung', color: 'purple' },
  APPROVED: { label: 'Đã duyệt', color: 'green' },
  REJECTED: { label: 'Từ chối', color: 'red' },
};

export const RESULT_STATUS: Record<string, Badge> = {
  DRAFT: { label: 'Kết quả dự kiến – chờ xác nhận', color: 'amber' },
  CONFIRMED: { label: 'Đã xác nhận', color: 'green' },
  SUPERSEDED: { label: 'Đã thay thế', color: 'gray' },
};

export const ROLE_LABEL: Record<Role, string> = {
  ADMIN: 'Quản trị viên',
  STAFF: 'Nhân viên',
  AUCTIONEER: 'Đấu giá viên',
  BIDDER: 'Người tham gia',
};

export const REVIEW_LABEL: Record<string, string> = {
  DOCUMENT_CHECK: 'Giấy tờ hợp lệ',
  ELIGIBILITY_CHECK: 'Đủ điều kiện theo quy chế',
  DEPOSIT_CHECK: 'Tiền đặt trước đã nhận',
  APPROVE: 'Duyệt hồ sơ',
  REQUEST_SUPPLEMENT: 'Yêu cầu bổ sung',
  REJECT: 'Từ chối',
};

export const FILE_TYPE_LABEL: Record<string, string> = {
  IDENTITY_DOCUMENT: 'Giấy tờ tùy thân',
  DEPOSIT_RECEIPT: 'Chứng từ tiền đặt trước',
  ASSET_IMAGE: 'Ảnh tài sản',
  ASSET_DOCUMENT: 'Tài liệu tài sản',
  OTHER: 'Khác',
};

export function fileSize(n: number | null): string {
  if (!n) return '';
  return n > 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)} MB` : `${Math.ceil(n / 1024)} KB`;
}
