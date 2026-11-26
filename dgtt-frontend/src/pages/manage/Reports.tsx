import { useState } from 'react';
import { api, downloadFile } from '../../api/client';
import type { ActivityLog, Page, ReportSummary } from '../../api/types';
import { useAuth } from '../../auth/AuthContext';
import { ErrorBox, Loading, Pager, useLoad } from '../../components/ui';
import { ASSET_STATUS, dt, REG_STATUS, SESSION_STATUS, vnd } from '../../format';

// Thống kê và báo cáo (FR-24, FR-25) cho Nhân viên, Quản trị viên; nhật ký hoạt động (FR-26) chỉ Quản trị viên.
// Khoảng thời gian chọn theo ngày GMT+7, gửi backend dạng [from, to) có múi giờ.
function range(from: string, to: string) {
  const q: Record<string, string> = {};
  if (from) q.from = `${from}T00:00:00+07:00`;
  if (to) {
    const d = new Date(`${to}T00:00:00+07:00`);
    d.setUTCDate(d.getUTCDate() + 1); // tính cả ngày "đến"
    q.to = d.toISOString();
  }
  return q;
}

function CountTable({ title, data, labels }: { title: string; data: Record<string, number>; labels: Record<string, { label: string }> }) {
  const total = Object.values(data).reduce((a, b) => a + b, 0);
  return (
    <div className="card" style={{ flex: 1, minWidth: 220 }}>
      <div className="h2">{title}</div>
      <table className="kv"><tbody>
        {Object.entries(labels).map(([k, v]) => (
          <tr key={k}><td>{v.label}</td><td style={{ textAlign: 'right' }}><b>{data[k] ?? 0}</b></td></tr>
        ))}
        <tr><td><b>Tổng</b></td><td style={{ textAlign: 'right' }}><b>{total}</b></td></tr>
      </tbody></table>
    </div>
  );
}

export default function Reports() {
  const { user } = useAuth();
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [applied, setApplied] = useState({ from: '', to: '' });
  const [exportErr, setExportErr] = useState<unknown>(null);
  const sum = useLoad(() => api<ReportSummary>('/reports/summary', { query: range(applied.from, applied.to) }), [applied]);
  const exp = (format: 'csv' | 'pdf') => {
    setExportErr(null);
    downloadFile('/reports/results/export', { format, ...range(applied.from, applied.to) }, `bao-cao-ket-qua.${format}`).catch(setExportErr);
  };
  const s = sum.data;
  return (
    <div className="col">
      <div className="h1">Thống kê và báo cáo</div>
      <form className="card row" style={{ gap: 10, alignItems: 'flex-end', flexWrap: 'wrap' }} onSubmit={(e) => { e.preventDefault(); setApplied({ from, to }); }}>
        <label className="col" style={{ gap: 4, fontSize: 12, fontWeight: 600 }}>Từ ngày<input className="in" type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></label>
        <label className="col" style={{ gap: 4, fontSize: 12, fontWeight: 600 }}>Đến ngày<input className="in" type="date" value={to} onChange={(e) => setTo(e.target.value)} /></label>
        <button className="btn p">Xem thống kê</button>
        <div className="sp" />
        <button type="button" className="btn" onClick={() => exp('csv')}>Xuất CSV</button>
        <button type="button" className="btn" onClick={() => exp('pdf')}>Xuất PDF</button>
      </form>
      <ErrorBox error={sum.error ?? exportErr} />
      {sum.loading && <Loading />}
      {s && (
        <>
          <div className="row" style={{ flexWrap: 'wrap' }}>
            <div className="card" style={{ flex: 1, minWidth: 220 }}>
              <div className="mut">Tổng giá trúng đã xác nhận</div>
              <div style={{ fontSize: 26, fontWeight: 700, color: 'var(--jade)' }}>{vnd(s.total_confirmed_amount)}</div>
            </div>
            <div className="card" style={{ flex: 1, minWidth: 220 }}>
              <div className="mut">Phiên chờ xác nhận kết quả</div>
              <div style={{ fontSize: 26, fontWeight: 700, color: 'var(--brass)' }}>{s.session_results.awaiting_confirmation}</div>
            </div>
            <div className="card" style={{ flex: 1, minWidth: 220 }}>
              <div className="mut">Phiên có người trúng / không thành</div>
              <div style={{ fontSize: 26, fontWeight: 700 }}>{s.session_results.confirmed_with_winner} / {s.session_results.confirmed_failed}</div>
            </div>
          </div>
          <div className="row" style={{ flexWrap: 'wrap', alignItems: 'flex-start' }}>
            <CountTable title="Tài sản theo trạng thái" data={s.assets_by_status} labels={ASSET_STATUS} />
            <CountTable title="Hồ sơ theo trạng thái" data={s.registrations_by_status} labels={REG_STATUS} />
            <CountTable title="Phiên theo trạng thái" data={s.sessions_by_status} labels={SESSION_STATUS} />
          </div>
          <div className="mut">Lập lúc {dt(s.generated_at)}. Giá trúng chỉ cộng các kết quả đã được Đấu giá viên xác nhận.</div>
        </>
      )}
      {user?.role === 'ADMIN' && <ActivityLogs />}
    </div>
  );
}

function ActivityLogs() {
  const [action, setAction] = useState('');
  const [entity, setEntity] = useState('');
  const [q, setQ] = useState({ action: '', entity_type: '' });
  const [page, setPage] = useState(1);
  const logs = useLoad(() => api<Page<ActivityLog>>('/activity-logs', { query: { ...q, page, size: 20 } }), [q, page]);
  return (
    <div className="card col">
      <div className="h2" style={{ margin: 0 }}>Nhật ký hoạt động (chỉ đọc)</div>
      <form className="row" style={{ gap: 8 }} onSubmit={(e) => { e.preventDefault(); setPage(1); setQ({ action: action.trim(), entity_type: entity.trim() }); }}>
        <input className="in" placeholder="Thao tác, ví dụ APPROVE_REGISTRATION" value={action} onChange={(e) => setAction(e.target.value)} />
        <input className="in" placeholder="Đối tượng, ví dụ registration, asset" value={entity} onChange={(e) => setEntity(e.target.value)} />
        <button className="btn">Lọc</button>
      </form>
      <ErrorBox error={logs.error} />
      {logs.loading && <Loading />}
      {logs.data && (
        <table>
          <thead><tr><th>Thời điểm</th><th>Người thực hiện</th><th>Thao tác</th><th>Đối tượng</th><th>Thay đổi</th><th>Lý do</th></tr></thead>
          <tbody>
            {logs.data.items.length === 0 && <tr><td colSpan={6} className="mut">Không có dòng nhật ký phù hợp.</td></tr>}
            {logs.data.items.map((l) => (
              <tr key={l.log_id}>
                <td className="mut">{dt(l.created_at)}</td>
                <td>{l.user_id ? `#${l.user_id}` : 'Hệ thống'}</td>
                <td>{l.action}</td>
                <td>{l.entity_type}{l.entity_id ? ` #${l.entity_id}` : ''}</td>
                <td className="mut">{l.field_name ? `${l.field_name}: ${l.old_value ?? '∅'} → ${l.new_value ?? '∅'}` : ''}</td>
                <td className="mut">{l.reason ?? ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {logs.data && <Pager page={logs.data.page} size={logs.data.size} total={logs.data.total} onPage={setPage} />}
    </div>
  );
}
