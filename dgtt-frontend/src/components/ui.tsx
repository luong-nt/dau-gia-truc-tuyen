import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { ApiError } from '../api/client';
import type { Role } from '../api/types';
import { useAuth } from '../auth/AuthContext';

export function Badge({ color, children }: { color: string; children: ReactNode }) {
  return <span className={`b ${color}`}>{children}</span>;
}

export function ErrorBox({ error }: { error: unknown }) {
  if (!error) return null;
  const msg = error instanceof Error ? error.message : String(error);
  return <div className="err-box">{msg}</div>;
}

export function Loading() {
  return <div className="mut" style={{ padding: 20 }}>Đang tải…</div>;
}

/** Gọi API khi vào trang; trả về dữ liệu, lỗi và hàm tải lại. */
export function useLoad<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const load = useCallback(fn, deps);
  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await load());
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [load]);
  useEffect(() => {
    reload();
  }, [reload]);
  return { data, error, loading, reload, setData };
}

/** Chặn trang theo vai trò. Ẩn trên giao diện chỉ để điều hướng; máy chủ vẫn kiểm tra quyền (UI-05). */
export function RequireRole({ roles, children }: { roles?: Role[]; children: ReactNode }) {
  const { user, ready } = useAuth();
  const loc = useLocation();
  if (!ready) return <Loading />;
  if (!user) return <Navigate to={`/login?next=${encodeURIComponent(loc.pathname + loc.search)}`} replace />;
  if (roles && !roles.includes(user.role))
    return (
      <div className="wrap">
        <div className="err-box">Tài khoản của bạn không có quyền truy cập trang này.</div>
      </div>
    );
  return <>{children}</>;
}

export function Pager({ page, size, total, onPage }: { page: number; size: number; total: number; onPage: (p: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / size));
  if (pages <= 1) return null;
  return (
    <div className="pager">
      <button className="btn" disabled={page <= 1} onClick={() => onPage(page - 1)}>‹ Trước</button>
      <span className="mut">Trang {page}/{pages}</span>
      <button className="btn" disabled={page >= pages} onClick={() => onPage(page + 1)}>Sau ›</button>
    </div>
  );
}

/** Hộp thoại nhập lý do / xác nhận cho thao tác quan trọng (UI-08). */
export function ReasonDialog(props: {
  title: string;
  message?: ReactNode;
  requireReason?: boolean;
  reasonLabel?: string;
  confirmText: string;
  danger?: boolean;
  extra?: ReactNode;
  onConfirm: (reason: string) => Promise<void>;
  onClose: () => void;
}) {
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const missing = props.requireReason && !reason.trim();
  return (
    <div className="dialog-bg" onClick={props.onClose}>
      <div className="dialog form" onClick={(e) => e.stopPropagation()}>
        <div className="h2">{props.title}</div>
        {props.message && <div className="mut" style={{ fontSize: 13 }}>{props.message}</div>}
        {props.extra}
        <label>
          {props.reasonLabel ?? 'Lý do'}
          {props.requireReason ? ' *' : ' (không bắt buộc)'}
          <textarea className="in" value={reason} onChange={(e) => setReason(e.target.value)} />
        </label>
        <ErrorBox error={err} />
        <div className="row" style={{ justifyContent: 'flex-end', gap: 8 }}>
          <button className="btn" onClick={props.onClose}>Hủy</button>
          <button
            className={`btn ${props.danger ? 'r' : 'p'}`}
            disabled={busy || missing}
            title={missing ? 'Vui lòng nhập lý do' : undefined}
            onClick={async () => {
              setBusy(true);
              setErr(null);
              try {
                await props.onConfirm(reason.trim());
                props.onClose();
              } catch (e) {
                setErr(e);
              } finally {
                setBusy(false);
              }
            }}
          >
            {busy ? 'Đang xử lý…' : props.confirmText}
          </button>
        </div>
      </div>
    </div>
  );
}

export function isForbidden(e: unknown) {
  return e instanceof ApiError && (e.status === 403 || e.status === 401);
}
