/**
 * Lớp gọi API dùng chung.
 * - Gắn token Bearer, nhận token gia hạn trong header X-Access-Token (NFR-04).
 * - Lỗi backend có dạng {code, message, details}; được ném ra dưới dạng ApiError.
 */
const TOKEN_KEY = 'dgtt_token';
export const API = '/api/v1';

export class ApiError extends Error {
  status: number;
  code: string;
  details: unknown;
  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn;
}

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}
export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* trình duyệt chặn lưu trữ: chỉ giữ trong phiên hiện tại */
  }
}

function describeValidation(details: unknown): string | null {
  // FastAPI trả danh sách lỗi kiểm tra dữ liệu; ghép thành một dòng dễ đọc
  if (!Array.isArray(details)) return null;
  const parts = details
    .map((d: { loc?: unknown[]; msg?: string }) => {
      const field = Array.isArray(d.loc) ? d.loc.filter((x) => x !== 'body').join('.') : '';
      return field ? `${field}: ${d.msg}` : d.msg;
    })
    .filter(Boolean);
  return parts.length ? parts.join('; ') : null;
}

type Options = {
  method?: string;
  body?: unknown;
  form?: FormData;
  query?: Record<string, string | number | boolean | undefined | null>;
  raw?: boolean;
};

export async function api<T = unknown>(path: string, opts: Options = {}): Promise<T> {
  const url = new URL(API + path, window.location.origin);
  Object.entries(opts.query ?? {}).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, String(v));
  });
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  let body: BodyInit | undefined;
  if (opts.form) body = opts.form;
  else if (opts.body !== undefined) {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(opts.body);
  }

  let res: Response;
  try {
    res = await fetch(url.pathname + url.search, { method: opts.method ?? 'GET', headers, body });
  } catch {
    throw new ApiError(0, 'NETWORK', 'Không kết nối được máy chủ. Kiểm tra mạng hoặc backend.');
  }

  const refreshed = res.headers.get('X-Access-Token');
  if (refreshed) setToken(refreshed);

  if (!res.ok) {
    let payload: { code?: string; message?: string; details?: unknown; detail?: unknown } = {};
    try {
      payload = await res.json();
    } catch {
      /* phản hồi không phải JSON */
    }
    const detailText = describeValidation(payload.details ?? payload.detail);
    let message = payload.message ?? detailText ?? `Lỗi ${res.status}`;
    if (payload.code === 'VALIDATION_ERROR' && detailText) message = `${message} (${detailText})`;
    const err = new ApiError(res.status, payload.code ?? `HTTP_${res.status}`, message, payload.details);
    if (res.status === 401 && onUnauthorized) onUnauthorized();
    throw err;
  }
  if (opts.raw) return res as unknown as T;
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/** Tải tệp có kèm token (ví dụ giấy tờ hồ sơ, danh sách đủ điều kiện). */
export async function downloadFile(path: string, query?: Options['query'], fallbackName = 'tep') {
  const res = await api<Response>(path, { query, raw: true });
  const blob = await res.blob();
  const cd = res.headers.get('Content-Disposition') ?? '';
  const m = /filename\*=UTF-8''([^;]+)|filename="?([^";]+)"?/i.exec(cd);
  const name = m ? decodeURIComponent(m[1] ?? m[2]) : fallbackName;
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

/** Địa chỉ WebSocket phòng đấu giá (đi qua proxy của Vite khi dev). */
export function roomSocketUrl(sessionId: number): string {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return `${proto}://${window.location.host}/ws/sessions/${sessionId}?token=${encodeURIComponent(getToken() ?? '')}`;
}
