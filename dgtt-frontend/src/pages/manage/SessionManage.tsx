import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api, downloadFile } from '../../api/client';
import type { EligibleList, PublicBid, Result, Session, SessionStatus } from '../../api/types';
import { useAuth } from '../../auth/AuthContext';
import { Badge, ErrorBox, Loading, ReasonDialog, useLoad } from '../../components/ui';
import { dt, parseUtc, RESULT_STATUS, SESSION_STATUS, timeOnly, vnd } from '../../format';

// SCR-09 – Điều hành phiên và xác nhận kết quả (FR-14, FR-17, FR-21 – FR-23) + thao tác của Nhân viên (FR-16)
type Action = { key: string; label: string; path: string; target: SessionStatus; reason: 'required' | 'optional' | 'none'; danger?: boolean };

function actionsFor(role: string, s: Session): Action[] {
  const a: Action[] = [];
  const running = s.status === 'IN_PROGRESS' || s.status === 'PAUSED';
  const early = running && (parseUtc(s.end_time)?.getTime() ?? 0) > Date.now();
  if (role === 'STAFF') {
    if (s.status === 'DRAFT') a.push({ key: 'publish', label: 'Công khai phiên', path: 'publish', target: 'OPEN_FOR_REGISTRATION', reason: 'none' });
    if (['DRAFT', 'OPEN_FOR_REGISTRATION', 'UPCOMING'].includes(s.status)) a.push({ key: 'cancel', label: 'Hủy phiên…', path: 'cancel', target: 'CANCELLED', reason: 'required', danger: true });
  }
  if (role === 'AUCTIONEER') {
    if (s.status === 'UPCOMING') a.push({ key: 'open', label: 'Mở phiên', path: 'open', target: 'IN_PROGRESS', reason: 'none' });
    if (s.status === 'IN_PROGRESS') a.push({ key: 'pause', label: 'Tạm dừng…', path: 'pause', target: 'PAUSED', reason: 'required' });
    if (s.status === 'PAUSED') a.push({ key: 'resume', label: 'Tiếp tục', path: 'resume', target: 'IN_PROGRESS', reason: 'optional' });
    if (running) a.push({ key: 'end', label: 'Kết thúc sớm…', path: 'end', target: 'ENDED', reason: early ? 'required' : 'optional', danger: true });
    if (running) a.push({ key: 'cancel', label: 'Hủy phiên…', path: 'cancel', target: 'CANCELLED', reason: 'required', danger: true });
  }
  return a;
}

export default function SessionManage() {
  const { id } = useParams();
  const sid = Number(id);
  const { user } = useAuth();
  const role = user?.role ?? '';
  const sess = useLoad(() => api<Session>(`/sessions/${sid}`), [sid]);
  const s = sess.data;
  const internal = role === 'STAFF' || role === 'AUCTIONEER';
  const eligible = useLoad(() => (internal ? api<EligibleList>(`/sessions/${sid}/eligible-bidders`) : Promise.resolve(null)), [sid, internal]);
  const showResults = s && (s.status === 'ENDED');
  const results = useLoad(() => (showResults ? api<Result[]>(`/sessions/${sid}/results`) : Promise.resolve([] as Result[])), [sid, showResults]);
  const showLog = s && ['IN_PROGRESS', 'PAUSED', 'ENDED'].includes(s.status) && role !== 'STAFF';
  const log = useLoad(() => (showLog ? api<PublicBid[]>(`/sessions/${sid}/bids`, { query: { include_rejected: true, limit: 200 } }) : Promise.resolve([] as PublicBid[])), [sid, showLog]);
  const [dialog, setDialog] = useState<Action | null>(null);
  const [resultDialog, setResultDialog] = useState<'confirm' | 'adjust' | null>(null);
  const [adjBid, setAdjBid] = useState('');
  const [err, setErr] = useState<unknown>(null);

  if (sess.loading) return <Loading />;
  if (!s) return <ErrorBox error={sess.error} />;
  const st = SESSION_STATUS[s.status];
  const actions = actionsFor(role, s);
  const draft = results.data?.find((r) => r.status === 'DRAFT');
  const confirmed = results.data?.find((r) => r.status === 'CONFIRMED');
  const rejectedCount = log.data?.filter((b) => b.result === 'REJECTED').length ?? 0;
  const acceptedCount = log.data?.filter((b) => b.result === 'ACCEPTED').length ?? 0;

  const doAction = async (a: Action, reason: string) => {
    await api(`/sessions/${sid}/${a.path}`, { method: 'POST', body: a.reason === 'none' ? undefined : { reason: reason || null } });
    await sess.reload();
  };

  return (
    <>
      <div className="mut" style={{ marginBottom: 8 }}><Link to="/manage/sessions">Phiên đấu giá</Link> › {s.code}</div>
      <div className="card" style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14, flexWrap: 'wrap' }}>
        <div>
          <div className="h1" style={{ marginBottom: 0 }}>{s.code} · {s.asset_name}</div>
          <span className="mut">Trạng thái: </span><Badge color={st.color}>{st.label}</Badge>
        </div>
        <div className="sp" style={{ flex: 1 }} />
        {['IN_PROGRESS', 'PAUSED', 'UPCOMING'].includes(s.status) && <Link className="btn" to={`/room/${sid}`}>Xem phòng đấu giá</Link>}
        {role === 'STAFF' && ['DRAFT', 'OPEN_FOR_REGISTRATION', 'UPCOMING'].includes(s.status) && <Link className="btn" to={`/manage/sessions/${sid}/edit`}>Sửa phiên</Link>}
        {role === 'STAFF' && <Link className="btn" to={`/manage/registrations?session_id=${sid}`}>Xét duyệt hồ sơ</Link>}
        {actions.map((a) => (
          <button key={a.key} className={`btn ${a.danger ? 'r' : a.key === 'publish' || a.key === 'open' ? 'p' : ''}`} onClick={() => setDialog(a)}>{a.label}</button>
        ))}
      </div>
      <ErrorBox error={err} />
      <div className="row">
        <div className="col" style={{ flex: 1.3 }}>
          <div className="card">
            <div className="h2">Cấu hình phiên</div>
            <table className="kv"><tbody>
              <tr><td>Giá khởi điểm / Bước giá</td><td><b>{vnd(s.starting_price)}</b> / <b>{vnd(s.bid_increment)}</b></td></tr>
              <tr><td>Tiền đặt trước</td><td>{vnd(s.deposit_amount)}</td></tr>
              <tr><td>Hạn nhận hồ sơ / nộp tiền</td><td>{dt(s.registration_deadline)} / {dt(s.deposit_deadline)}</td></tr>
              <tr><td>Thời gian tổ chức</td><td>{dt(s.start_time)} – {dt(s.end_time)}</td></tr>
              <tr><td>Mã tài sản / Đấu giá viên</td><td>#{s.asset_id} / #{s.auctioneer_id}</td></tr>
            </tbody></table>
          </div>
          {showLog && (
            <div className="card">
              <div className="h2">Nhật ký diễn biến (gồm lệnh bị từ chối)</div>
              <ErrorBox error={log.error} />
              <div style={{ maxHeight: 340, overflowY: 'auto' }}>
                <table>
                  <thead><tr><th>Giờ máy chủ</th><th>Lượt</th><th>Chủ thể</th><th>Nội dung</th></tr></thead>
                  <tbody>
                    {log.data?.map((b) => (
                      <tr key={b.sequence_no}>
                        <td>{timeOnly(b.server_time)}</td>
                        <td>#{b.sequence_no}</td>
                        <td>{b.bidder_alias}</td>
                        <td>
                          {b.result === 'ACCEPTED'
                            ? <Badge color="green">{vnd(b.amount)} — Chấp nhận</Badge>
                            : <Badge color="red">{vnd(b.amount)} — Từ chối: {b.rejection_reason}</Badge>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {log.data?.length === 0 && <div className="mut" style={{ padding: 8 }}>Chưa có lệnh giá.</div>}
              </div>
              <button className="btn" style={{ marginTop: 8 }} onClick={log.reload}>Làm mới</button>
            </div>
          )}
          {internal && (
            <div className="card">
              <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center', flexDirection: 'row' }}>
                <div className="h2">Người đủ điều kiện ({eligible.data?.total ?? 0})</div>
                <div className="row" style={{ gap: 6, flexDirection: 'row' }}>
                  <button className="btn" onClick={() => downloadFile(`/sessions/${sid}/eligible-bidders/export`, { format: 'csv' }, `du-dieu-kien-${s.code}.csv`).catch(setErr)}>Xuất CSV</button>
                  <button className="btn" onClick={() => downloadFile(`/sessions/${sid}/eligible-bidders/export`, { format: 'pdf' }, `du-dieu-kien-${s.code}.pdf`).catch(setErr)}>Xuất PDF</button>
                </div>
              </div>
              <ErrorBox error={eligible.error} />
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(150px,1fr))', gap: 6 }}>
                {eligible.data?.items.map((e) => (
                  <div key={e.registration_id} style={{ border: '1px solid #e5e7eb', borderRadius: 6, padding: 6, fontSize: 12 }}>
                    <b>{e.bidder_alias}</b> · {e.full_name}
                  </div>
                ))}
              </div>
              {eligible.data?.items.length === 0 && <div className="mut">Chưa có người được duyệt.</div>}
            </div>
          )}
        </div>
        {showResults && (
          <div className="col" style={{ flex: 1 }}>
            <div className="card" style={{ border: '2px solid #1d4ed8' }}>
              <ErrorBox error={results.error} />
              {(draft ?? confirmed) ? (() => {
                const r = (draft ?? confirmed)!;
                return (
                  <>
                    <Badge color={RESULT_STATUS[r.status].color}>{RESULT_STATUS[r.status].label}</Badge>
                    <span className="mut"> · Phiên bản {r.version_no}</span>
                    <div className="mut" style={{ marginTop: 10 }}>Giá cao nhất đã chấp nhận</div>
                    <div style={{ fontSize: 30, fontWeight: 700 }}>{r.winning_amount ? vnd(r.winning_amount) : 'Không có giá hợp lệ'}</div>
                    <table className="kv" style={{ marginTop: 8 }}><tbody>
                      <tr><td>Người trả giá cao nhất</td><td><b>{r.winning_bidder_alias ?? '—'}</b></td></tr>
                      <tr><td>Lượt chấp nhận / bị từ chối</td><td>{acceptedCount} / {rejectedCount}</td></tr>
                      {r.exception_note && <tr><td>Ghi nhận ngoại lệ</td><td>{r.exception_note}</td></tr>}
                      {r.adjustment_reason && <tr><td>Lý do điều chỉnh</td><td>{r.adjustment_reason}</td></tr>}
                      {r.confirmed_at && <tr><td>Xác nhận lúc</td><td>{dt(r.confirmed_at)}</td></tr>}
                    </tbody></table>
                    {role === 'AUCTIONEER' && r.status === 'DRAFT' && (
                      <button className="btn p" style={{ width: '100%', marginTop: 12 }} onClick={() => setResultDialog('confirm')}>Xác nhận kết quả</button>
                    )}
                    {role === 'AUCTIONEER' && !draft && confirmed && (
                      <button className="btn o" style={{ width: '100%', marginTop: 12 }} onClick={() => setResultDialog('adjust')}>Điều chỉnh kết quả…</button>
                    )}
                    <div className="mut" style={{ marginTop: 8 }}>Xác nhận trên phần mềm không thay thế chữ ký pháp lý. Điều chỉnh sau xác nhận sẽ tạo phiên bản mới có lý do.</div>
                  </>
                );
              })() : <div className="mut">Chưa có bản kết quả.</div>}
            </div>
            {results.data && results.data.length > 1 && (
              <div className="card">
                <div className="h2">Các phiên bản kết quả</div>
                {results.data.map((r) => (
                  <div key={r.result_id} style={{ fontSize: 13, padding: '4px 0' }}>
                    v{r.version_no} · <Badge color={RESULT_STATUS[r.status].color}>{RESULT_STATUS[r.status].label}</Badge> · {r.winning_bidder_alias ?? '—'} {r.winning_amount ? vnd(r.winning_amount) : ''}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {dialog && (
        <ReasonDialog
          title={dialog.label.replace('…', '')}
          message={`Chuyển phiên ${s.code} sang trạng thái "${SESSION_STATUS[dialog.target].label}".`}
          requireReason={dialog.reason === 'required'}
          confirmText="Xác nhận"
          danger={dialog.danger}
          onConfirm={(reason) => doAction(dialog, reason)}
          onClose={() => setDialog(null)}
        />
      )}
      {resultDialog === 'confirm' && draft && (
        <ReasonDialog
          title="Xác nhận kết quả đấu giá"
          message="Kiểm tra diễn biến và sự cố trước khi xác nhận. Hệ thống không tự công bố người trúng."
          reasonLabel="Ghi nhận xử lý ngoại lệ"
          confirmText="Xác nhận kết quả"
          onConfirm={async (note) => {
            await api(`/sessions/${sid}/results/${draft.result_id}/confirm`, { method: 'POST', body: { exception_note: note || null } });
            await results.reload();
          }}
          onClose={() => setResultDialog(null)}
        />
      )}
      {resultDialog === 'adjust' && (
        <ReasonDialog
          title="Điều chỉnh kết quả (tạo phiên bản mới)"
          requireReason
          reasonLabel="Lý do điều chỉnh"
          confirmText="Tạo bản điều chỉnh"
          danger
          extra={
            <label>
              Mã lượt giá trúng (bid_id) – để trống nếu không có người trúng
              <input className="in" type="number" value={adjBid} onChange={(e) => setAdjBid(e.target.value)} />
            </label>
          }
          onConfirm={async (reason) => {
            await api(`/sessions/${sid}/results`, { method: 'POST', body: { winning_bid_id: adjBid ? Number(adjBid) : null, adjustment_reason: reason } });
            await results.reload();
          }}
          onClose={() => setResultDialog(null)}
        />
      )}
    </>
  );
}
