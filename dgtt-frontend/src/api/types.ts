// Kiểu dữ liệu khớp với schemas của dgtt-backend (app/modules/*/schemas.py).
// Tiền (Decimal) được backend trả về dạng chuỗi, ví dụ "1E+8" -> dùng money() để đọc.
// Thời gian là UTC không kèm múi giờ -> dùng parseUtc() trước khi hiển thị GMT+7.

export type Role = 'ADMIN' | 'STAFF' | 'AUCTIONEER' | 'BIDDER';
export type SessionStatus =
  | 'DRAFT'
  | 'OPEN_FOR_REGISTRATION'
  | 'UPCOMING'
  | 'IN_PROGRESS'
  | 'PAUSED'
  | 'ENDED'
  | 'CANCELLED';
export type RegistrationStatus = 'PENDING' | 'NEEDS_SUPPLEMENT' | 'APPROVED' | 'REJECTED';
export type ReviewType =
  | 'DOCUMENT_CHECK'
  | 'ELIGIBILITY_CHECK'
  | 'DEPOSIT_CHECK'
  | 'APPROVE'
  | 'REQUEST_SUPPLEMENT'
  | 'REJECT';
export type Money = string | number;

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
}

export interface User {
  user_id: number;
  role: Role;
  username: string;
  email: string;
  phone: string | null;
  full_name: string;
  status: 'ACTIVE' | 'LOCKED';
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export interface Session {
  session_id: number;
  code: string;
  asset_id: number;
  auctioneer_id: number;
  starting_price: Money;
  bid_increment: Money;
  deposit_amount: Money;
  registration_deadline: string;
  deposit_deadline: string;
  start_time: string;
  end_time: string;
  status: SessionStatus;
  notice_content: string | null;
  asset_code?: string;
  asset_name?: string;
}

export interface Attachment {
  attachment_id: number;
  file_type: string;
  file_name: string;
  file_format: string | null;
  file_size: number | null;
  submission_no: number | null;
  uploaded_at: string;
}

export interface Review {
  review_id?: number;
  registration_id?: number;
  reviewed_by?: number;
  evidence?: string | null;
  review_type: ReviewType;
  result: 'PASSED' | 'FAILED' | null;
  reason: string | null;
  reviewed_at: string;
}

export interface Registration {
  registration_id: number;
  session_id: number;
  session_code: string;
  submitted_full_name: string;
  submitted_id_number: string;
  submitted_address: string | null;
  submitted_phone: string | null;
  submission_count: number;
  status: RegistrationStatus;
  supplement_deadline: string | null;
  bidder_alias: string | null;
  submitted_at: string;
  attachments: Attachment[];
  reviews: Review[];
}

export interface EligibleList {
  session_id: number;
  session_code: string;
  asset_name: string;
  total: number;
  items: { registration_id: number; bidder_alias: string; full_name: string; approved_at: string | null }[];
}

export interface PublicBid {
  sequence_no: number;
  bidder_alias: string | null;
  amount: Money;
  result: 'ACCEPTED' | 'REJECTED';
  rejection_reason?: string | null;
  server_time: string;
}

export interface RoomState {
  session_id: number;
  code: string;
  status: SessionStatus;
  starting_price: Money;
  bid_increment: Money;
  highest_accepted: Money | null;
  minimum_next_bid: Money;
  start_time: string;
  end_time: string;
  server_time: string;
  my_alias: string | null;
  recent_bids: PublicBid[];
}

export interface BidOut {
  bid_id: number;
  transaction_code: string;
  amount: Money;
  result: 'ACCEPTED' | 'REJECTED';
  rejection_reason: string | null;
  sequence_no: number;
  server_time: string;
  duplicated: boolean;
}

export interface Result {
  result_id: number;
  session_id: number;
  version_no: number;
  winning_bid_id: number | null;
  status: 'DRAFT' | 'CONFIRMED' | 'SUPERSEDED';
  exception_note: string | null;
  adjustment_reason: string | null;
  confirmed_by: number | null;
  confirmed_at: string | null;
  minutes_url: string | null;
  winning_amount: Money | null;
  winning_bidder_alias: string | null;
}

// ---- Tài sản (FR-05 – FR-07), backend TASK-007, TASK-008, TASK-014
export type AssetStatus = 'UPCOMING' | 'IN_AUCTION' | 'ENDED' | 'SUSPENDED_CANCELLED';

export interface Asset {
  asset_id: number;
  asset_code: string;
  name: string;
  description: string | null;
  status: AssetStatus;
  is_public: boolean;
  created_at: string;
}

export interface AssetOwner {
  owner_id: number;
  owner_type: 'INDIVIDUAL' | 'ORGANIZATION';
  name: string;
  id_number: string;
  representative_name: string | null;
  phone: string | null;
  email: string | null;
  address: string | null;
  created_at: string;
}

export interface AssetAttachment {
  attachment_id: number;
  asset_id: number;
  file_type: 'ASSET_IMAGE' | 'ASSET_DOCUMENT';
  file_name: string;
  file_format: string | null;
  file_size: number | null;
  display_order: number | null;
  uploaded_at: string;
}

export interface AssetDetail extends Asset {
  owner: AssetOwner | null;
  sessions: { session_id: number; code: string; status: SessionStatus; starting_price: Money; start_time: string; end_time: string }[];
  attachments: AssetAttachment[];
}

// ---- Kết quả chính thức (FR-23), backend TASK-009
export interface OfficialResult {
  result_id: number;
  session_id: number;
  session_code: string;
  version_no: number;
  confirmed_at: string | null;
  is_failed: boolean;
  winning_bidder_alias: string | null;
  winning_amount: Money | null;
  exception_note: string | null;
  my_alias: string | null;
  is_mine: boolean;
}

// ---- Thống kê, nhật ký (FR-24 – FR-26), backend TASK-010, TASK-011
export interface ReportSummary {
  date_from: string | null;
  date_to: string | null;
  generated_at: string;
  assets_by_status: Record<string, number>;
  registrations_by_status: Record<string, number>;
  sessions_by_status: Record<string, number>;
  session_results: { awaiting_confirmation: number; confirmed_with_winner: number; confirmed_failed: number };
  total_confirmed_amount: Money;
}

export interface ActivityLog {
  log_id: number;
  user_id: number | null;
  action: string;
  entity_type: string;
  entity_id: number | null;
  field_name: string | null;
  old_value: string | null;
  new_value: string | null;
  reason: string | null;
  created_at: string;
}
