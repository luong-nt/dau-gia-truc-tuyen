import { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { api } from '../../api/client';
import type { Page, Registration } from '../../api/types';
import { Badge, ErrorBox, Loading, Pager, useLoad } from '../../components/ui';
import { dt, parseUtc, REG_STATUS, REVIEW_LABEL } from '../../format';

// SCR-05 – Hồ sơ đăng ký của tôi (FR-12, FR-13)
function depositState(r: Registration) {
  const d = r.reviews.filter((x) => x.review_type === 'DEPOSIT_CHECK').at(-1);
  if (r.status === 'APPROVED' || d?.result === 'PASSED') return <Badge color="green">Đã xác nhận</Badge>;
  return <Badge color="gray">Chưa xác nhận</Badge>;
}

export default function MyRegistrations() {
  const loc = useLocation() as { state?: { flash?: string } };
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<number | null>(null);
  const { data, error, loading } = useLoad(
    () => api<Page<Registration>>('/registrations/me', { query: { page, size: 20 } }),
    [page],
  );
  const current = data?.items.find((r) => r.registration_id === selected) ?? data?.items.find((r) => r.status === 'NEEDS_SUPPLEMENT') ?? data?.items[0];

  return (
    <div className="wrap">
      <div className="h1">Hồ sơ đăng ký của tôi</div>
      {loc.state?.flash && <div className="ok-box" style={{ margin: '10px 0' }}>{loc.state.flash}</div>}
      <ErrorBox error={error} />
      {loading && <Loading />}
      {data && data.items.length === 0 && (
        <div className="card mut" style={{ marginTop: 12 }}>Bạn chưa nộp hồ sơ nào. <Link to="/">Tìm phiên đang nhận hồ sơ</Link></div>
      )}
      {data && data.items.length > 0 && (
        <div className="col" style={{ marginTop: 12 }}>
          <div className="card" style={{ overflowX: 'auto' }}>
            <table>
              <thead>
                <tr><th>Mã hồ sơ</th><th>Phiên</th><th>Ngày nộp</th><th>Tiền đặt trước</th><th>Trạng thái</th><th></th></tr>
              </thead>
              <tbody>
                {data.items.map((r) => (
                  <tr key={r.registration_id} style={{ background: r.status === 'NEEDS_SUPPLEMENT' ? 'var(--brass-50)' : undefined, cursor: 'pointer' }} onClick={() => setSelected(r.registration_id)}>
                    <td>HS-{r.registration_id}</td>
                    <td><Link to={`/sessions/${r.session_id}`}>{r.session_code}</Link>{r.bidder_alias && <> · <b>{r.bidder_alias}</b></>}</td>
                    <td>{dt(r.submitted_at)}</td>
                    <td>{depositState(r)}</td>
                    <td><Badge color={REG_STATUS[r.status].color}>{REG_STATUS[r.status].label}</Badge></td>
                    <td>
                      {r.status === 'NEEDS_SUPPLEMENT' && <Link className="btn o" to={`/registrations/${r.registration_id}/supplement`}>Bổ sung</Link>}
                      {r.status === 'APPROVED' && <Link className="btn" to={`/room/${r.session_id}`}>Vào phòng</Link>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <Pager page={data.page} size={data.size} total={data.total} onPage={setPage} />
          </div>
          {current && (
            <div className="row">
              <div className="card" style={{ flex: 1 }}>
                <div className="h2">Phản hồi cho hồ sơ HS-{current.registration_id}</div>
                {current.status === 'NEEDS_SUPPLEMENT' ? (
                  <div className="warn">
                    <b>Lý do:</b> {current.reviews.filter((x) => x.review_type === 'REQUEST_SUPPLEMENT').at(-1)?.reason ?? '—'}<br />
                    <b>Hạn bổ sung:</b> {dt(current.supplement_deadline)}
                    {(parseUtc(current.supplement_deadline)?.getTime() ?? 0) < Date.now() && <> (đã hết hạn)</>}
                  </div>
                ) : current.status === 'REJECTED' ? (
                  <div className="err-box"><b>Lý do từ chối:</b> {current.reviews.filter((x) => x.review_type === 'REJECT').at(-1)?.reason ?? '—'}</div>
                ) : current.status === 'APPROVED' ? (
                  <div className="ok-box">Hồ sơ đã được duyệt. Mã tham gia của bạn trong phòng: <b>{current.bidder_alias}</b></div>
                ) : (
                  <div className="note">Hồ sơ đang chờ nhân viên xét duyệt.</div>
                )}
                <div className="mut" style={{ marginTop: 8 }}>Đã nộp {current.submission_count} lần · {current.attachments.length} tệp đính kèm</div>
              </div>
              <div className="card" style={{ flex: 1 }}>
                <div className="h2">Lịch sử hồ sơ</div>
                <div style={{ fontSize: 13, lineHeight: 2, borderLeft: '2px solid var(--line)', paddingLeft: 12 }}>
                  <div>{dt(current.submitted_at)} — Nộp hồ sơ</div>
                  {current.reviews.map((rv, i) => (
                    <div key={i}>
                      {dt(rv.reviewed_at)} — {REVIEW_LABEL[rv.review_type]}
                      {rv.result && <> : {rv.result === 'PASSED' ? 'Đạt' : 'Không đạt'}</>}
                      {rv.reason && <span className="mut"> ({rv.reason})</span>}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
