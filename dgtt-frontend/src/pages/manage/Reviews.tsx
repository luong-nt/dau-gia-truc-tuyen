import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { api, downloadFile } from '../../api/client';
import type { Page, Registration, RegistrationStatus, ReviewType } from '../../api/types';
import { Badge, ErrorBox, Loading, Pager, ReasonDialog, useLoad } from '../../components/ui';
import { dt, FILE_TYPE_LABEL, fileSize, fromLocalInput, REG_STATUS, REVIEW_LABEL } from '../../format';

// SCR-08 – Xét duyệt hồ sơ (FR-11, FR-12, FR-13)
const CHECKS: ReviewType[] = ['DOCUMENT_CHECK', 'ELIGIBILITY_CHECK', 'DEPOSIT_CHECK'];

export default function Reviews() {
  const [params, setParams] = useSearchParams();
  const sessionId = params.get('session_id') ?? '';
  const [status, setStatus] = useState<RegistrationStatus | ''>('PENDING');
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<number | null>(null);
  const list = useLoad(
    () => api<Page<Registration>>('/registrations', { query: { session_id: sessionId, status, page, size: 20 } }),
    [sessionId, status, page],
  );
  const detail = useLoad(() => (selected ? api<Registration>(`/registrations/${selected}`) : Promise.resolve(null)), [selected]);

  return (
    <>
      <div className="h1">Xét duyệt hồ sơ{sessionId && ` · phiên #${sessionId}`}</div>
      <div className="row" style={{ marginTop: 12 }}>
        <div className="card" style={{ width: 340, padding: 10, flex: 'none' }}>
          <div className="row" style={{ gap: 6, marginBottom: 8, flexDirection: 'row' }}>
            <input className="in" placeholder="Mã phiên (số)" value={sessionId} onChange={(e) => { setPage(1); setParams(e.target.value ? { session_id: e.target.value } : {}); }} style={{ flex: 1 }} />
            <select className="in" style={{ flex: 1 }} value={status} onChange={(e) => { setPage(1); setStatus(e.target.value as RegistrationStatus | ''); }}>
              <option value="">Tất cả</option>
              {Object.entries(REG_STATUS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
            </select>
          </div>
          <ErrorBox error={list.error} />
          {list.loading && <Loading />}
          {list.data?.items.map((r) => (
            <div
              key={r.registration_id}
              onClick={() => setSelected(r.registration_id)}
              style={{ padding: 9, borderRadius: 6, marginBottom: 4, cursor: 'pointer', border: '1px solid', borderColor: selected === r.registration_id ? '#bfdbfe' : 'transparent', background: selected === r.registration_id ? '#eff6ff' : undefined }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <b>HS-{r.registration_id}</b>
                <Badge color={REG_STATUS[r.status].color}>{REG_STATUS[r.status].label}</Badge>
              </div>
              <div className="mut">{r.submitted_full_name} · {r.session_code} · nộp {dt(r.submitted_at)}</div>
            </div>
          ))}
          {list.data?.items.length === 0 && <div className="mut" style={{ padding: 8 }}>Không có hồ sơ.</div>}
          {list.data && <Pager page={list.data.page} size={list.data.size} total={list.data.total} onPage={setPage} />}
        </div>
        <div className="col" style={{ flex: 1 }}>
          {!selected && <div className="card mut">Chọn một hồ sơ để xem và xét duyệt.</div>}
          {selected && detail.loading && <Loading />}
          <ErrorBox error={detail.error} />
          {detail.data && <ReviewPanel reg={detail.data} onChanged={async () => { await detail.reload(); await list.reload(); }} />}
        </div>
      </div>
    </>
  );
}

function ReviewPanel({ reg, onChanged }: { reg: Registration; onChanged: () => Promise<void> }) {
  const [check, setCheck] = useState<{ type: ReviewType; result: 'PASSED' | 'FAILED' } | null>(null);
  const [evidence, setEvidence] = useState('');
  const [decision, setDecision] = useState<'APPROVE' | 'REQUEST_SUPPLEMENT' | 'REJECT' | null>(null);
  const [deadline, setDeadline] = useState('');
  const [err, setErr] = useState<unknown>(null);

  const latest = (t: ReviewType) => reg.reviews.filter((r) => r.review_type === t).at(-1);
  const allPassed = CHECKS.every((t) => latest(t)?.result === 'PASSED');
  const pending = reg.status === 'PENDING';

  return (
    <>
      <div className="card">
        <div className="row" style={{ justifyContent: 'space-between', flexDirection: 'row' }}>
          <div className="h2">HS-{reg.registration_id} · {reg.submitted_full_name}</div>
          <Badge color={REG_STATUS[reg.status].color}>{REG_STATUS[reg.status].label}</Badge>
        </div>
        <div className="mut" style={{ marginBottom: 8 }}>Bản thông tin đã gửi lúc {dt(reg.submitted_at)} (lần nộp {reg.submission_count}) · Phiên {reg.session_code}</div>
        <table className="kv"><tbody>
          <tr><td>Số giấy tờ định danh</td><td>{reg.submitted_id_number}</td></tr>
          <tr><td>Địa chỉ</td><td>{reg.submitted_address ?? '—'}</td></tr>
          <tr><td>Điện thoại</td><td>{reg.submitted_phone ?? '—'}</td></tr>
          {reg.bidder_alias && <tr><td>Mã tham gia</td><td><b>{reg.bidder_alias}</b></td></tr>}
        </tbody></table>
        <div className="row" style={{ gap: 8, marginTop: 10, flexWrap: 'wrap', flexDirection: 'row' }}>
          {reg.attachments.map((a) => (
            <button key={a.attachment_id} className="btn" onClick={() => downloadFile(`/registrations/${reg.registration_id}/attachments/${a.attachment_id}`, undefined, a.file_name).catch(setErr)}>
              📄 {FILE_TYPE_LABEL[a.file_type] ?? a.file_type}: {a.file_name} {a.file_size ? `(${fileSize(a.file_size)})` : ''} {a.submission_no ? `· lần ${a.submission_no}` : ''}
            </button>
          ))}
        </div>
      </div>

      <div className="card">
        <div className="h2">Kết quả kiểm tra</div>
        <table>
          <thead><tr><th>Tiêu chí</th><th>Kết quả</th><th>Người kiểm tra / thời điểm</th><th></th></tr></thead>
          <tbody>
            {CHECKS.map((t) => {
              const r = latest(t);
              return (
                <tr key={t}>
                  <td>{REVIEW_LABEL[t]}{r?.reason && <div className="mut">{r.reason}</div>}{r?.evidence && <div className="mut">Căn cứ: {r.evidence}</div>}</td>
                  <td>{r?.result === 'PASSED' ? <Badge color="green">Đạt</Badge> : r?.result === 'FAILED' ? <Badge color="red">Không đạt</Badge> : <Badge color="gray">Chưa kiểm tra</Badge>}</td>
                  <td className="mut">{r ? `NV #${r.reviewed_by ?? '?'} · ${dt(r.reviewed_at)}` : '—'}</td>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    {pending && <>
                      <button className="btn" onClick={() => setCheck({ type: t, result: 'PASSED' })}>Đạt</button>{' '}
                      <button className="btn r" onClick={() => setCheck({ type: t, result: 'FAILED' })}>Không đạt</button>
                    </>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="card">
        <div className="h2">Quyết định</div>
        <ErrorBox error={err} />
        <div className="row" style={{ gap: 8, alignItems: 'flex-start', flexDirection: 'row', flexWrap: 'wrap' }}>
          <div style={{ flex: 1, minWidth: 160 }}>
            <button className="btn g" style={{ width: '100%' }} disabled={!pending || !allPassed} onClick={() => setDecision('APPROVE')}>✓ Duyệt hồ sơ</button>
            <div className="mut" style={{ marginTop: 4 }}>Chỉ bật khi cả ba tiêu chí đều Đạt</div>
          </div>
          <div style={{ flex: 1, minWidth: 160 }}>
            <button className="btn o" style={{ width: '100%' }} disabled={!pending} onClick={() => setDecision('REQUEST_SUPPLEMENT')}>Yêu cầu bổ sung</button>
            <div className="mut" style={{ marginTop: 4 }}>Bắt buộc nhập lý do và hạn bổ sung</div>
          </div>
          <div style={{ flex: 1, minWidth: 160 }}>
            <button className="btn r" style={{ width: '100%' }} disabled={!(pending || reg.status === 'NEEDS_SUPPLEMENT')} onClick={() => setDecision('REJECT')}>✕ Từ chối</button>
            <div className="mut" style={{ marginTop: 4 }}>Bắt buộc nhập lý do</div>
          </div>
        </div>
      </div>

      {check && (
        <ReasonDialog
          title={`${REVIEW_LABEL[check.type]}: ${check.result === 'PASSED' ? 'Đạt' : 'Không đạt'}`}
          requireReason={check.result === 'FAILED'}
          reasonLabel={check.result === 'FAILED' ? 'Lý do không đạt' : 'Ghi chú'}
          confirmText="Lưu kết quả kiểm tra"
          extra={check.type === 'DEPOSIT_CHECK' ? (
            <label>Căn cứ đối soát (số chứng từ, ngày ghi có){check.result === 'PASSED' ? ' *' : ''}<input className="in" value={evidence} onChange={(e) => setEvidence(e.target.value)} /></label>
          ) : undefined}
          onConfirm={async (reason) => {
            // FR-11 / SCR-08: xác nhận tiền đặt trước phải có căn cứ đối soát (BUG-001)
            if (check.type === 'DEPOSIT_CHECK' && check.result === 'PASSED' && !evidence.trim())
              throw new Error('Vui lòng nhập căn cứ đối soát (số chứng từ, ngày ghi có) trước khi xác nhận tiền đặt trước');
            await api(`/registrations/${reg.registration_id}/checks`, { method: 'POST', body: { review_type: check.type, result: check.result, reason: reason || null, evidence: evidence || null } });
            setEvidence('');
            await onChanged();
          }}
          onClose={() => setCheck(null)}
        />
      )}
      {decision && (
        <ReasonDialog
          title={REVIEW_LABEL[decision]}
          message={decision === 'APPROVE' ? 'Hệ thống sẽ cấp mã tham gia ẩn danh (NTG-xx) cho người này.' : undefined}
          requireReason={decision !== 'APPROVE'}
          confirmText={REVIEW_LABEL[decision]}
          danger={decision === 'REJECT'}
          extra={decision === 'REQUEST_SUPPLEMENT' ? (
            <label>Hạn bổ sung (GMT+7) *<input className="in" type="datetime-local" value={deadline} onChange={(e) => setDeadline(e.target.value)} /></label>
          ) : undefined}
          onConfirm={async (reason) => {
            if (decision === 'REQUEST_SUPPLEMENT' && !deadline) throw new Error('Vui lòng chọn hạn bổ sung');
            await api(`/registrations/${reg.registration_id}/decision`, {
              method: 'POST',
              body: { decision, reason: reason || null, supplement_deadline: decision === 'REQUEST_SUPPLEMENT' ? fromLocalInput(deadline) : null },
            });
            await onChanged();
          }}
          onClose={() => setDecision(null)}
        />
      )}
    </>
  );
}
