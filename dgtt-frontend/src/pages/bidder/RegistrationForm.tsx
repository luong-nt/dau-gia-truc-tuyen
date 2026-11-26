import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api } from '../../api/client';
import type { Page, Registration, Session } from '../../api/types';
import { useAuth } from '../../auth/AuthContext';
import { ErrorBox, Loading, useLoad } from '../../components/ui';
import { dt } from '../../format';

// SCR-04 – Nộp và bổ sung hồ sơ đăng ký phiên (FR-10, FR-11, FR-12)
// Khớp backend: multipart; identity_documents (≥1 tệp), deposit_receipt; PDF/JPG/PNG; tối đa 10 MB/tệp (MAX_UPLOAD_MB)
const ALLOWED = ['pdf', 'jpg', 'jpeg', 'png'];
const MAX_MB = 10;

function checkFile(f: File): string | null {
  const ext = f.name.split('.').pop()?.toLowerCase() ?? '';
  if (!ALLOWED.includes(ext)) return `${f.name}: chỉ chấp nhận PDF, JPG, PNG`;
  if (f.size > MAX_MB * 1024 * 1024) return `${f.name}: vượt quá ${MAX_MB} MB`;
  return null;
}

function Step({ n, label, on }: { n: number; label: string; on: boolean }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <span style={{ width: 26, height: 26, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: 12, background: on ? 'var(--jade)' : '#e5e7eb', color: on ? '#fff' : '#6b7280' }}>{n}</span>
      <span style={{ fontWeight: on ? 600 : 400 }}>{label}</span>
    </div>
  );
}

export default function RegistrationForm() {
  const { id, regId } = useParams();
  const resubmit = Boolean(regId);
  const { user } = useAuth();
  const nav = useNavigate();

  const { data, error, loading } = useLoad(async () => {
    if (resubmit) {
      const reg = await api<Registration>(`/registrations/${regId}`);
      const session = await api<Session>(`/sessions/${reg.session_id}`);
      return { reg, session };
    }
    const session = await api<Session>(`/sessions/${id}`);
    const mine = await api<Page<Registration>>('/registrations/me', { query: { size: 100 } });
    return { reg: mine.items.find((r) => r.session_id === session.session_id) ?? null, session };
  }, [id, regId]);

  const [step, setStep] = useState(1);
  const [info, setInfo] = useState<{ name: string; idn: string; addr: string; phone: string } | null>(null);
  const [ids, setIds] = useState<File[]>([]);
  const [receipt, setReceipt] = useState<File | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  if (loading) return <Loading />;
  if (error || !data) return <div className="wrap"><ErrorBox error={error} /></div>;
  const { reg, session } = data;

  // Mỗi người chỉ có 01 hồ sơ hiệu lực trong một phiên (FR-10)
  if (!resubmit && reg)
    return (
      <div className="wrap" style={{ maxWidth: 700, margin: '0 auto' }}>
        <div className="note">Bạn đã có hồ sơ cho phiên {session.code}. <Link to="/my/registrations">Xem hồ sơ của tôi</Link></div>
      </div>
    );
  if (resubmit && reg?.status !== 'NEEDS_SUPPLEMENT')
    return <div className="wrap"><div className="note">Hồ sơ này không ở trạng thái cần bổ sung.</div></div>;

  const form = info ?? {
    name: reg?.submitted_full_name ?? user?.full_name ?? '',
    idn: reg?.submitted_id_number ?? '',
    addr: reg?.submitted_address ?? '',
    phone: reg?.submitted_phone ?? user?.phone ?? '',
  };
  const setForm = (k: keyof typeof form, v: string) => setInfo({ ...form, [k]: v });
  const infoIssues: string[] = [];
  if (!form.name.trim()) infoIssues.push('Nhập họ và tên');
  if (!/^[0-9]{9,20}$/.test(form.idn)) infoIssues.push('Số giấy tờ định danh gồm 9–20 chữ số');
  if (form.phone && !/^[0-9+]{9,15}$/.test(form.phone)) infoIssues.push('Số điện thoại 9–15 chữ số');
  const fileIssues = [...ids, ...(receipt ? [receipt] : [])].map(checkFile).filter(Boolean) as string[];
  const missingIds = !resubmit && ids.length === 0;
  const lastReason = reg?.reviews.filter((r) => r.review_type === 'REQUEST_SUPPLEMENT').at(-1)?.reason;

  const submit = async () => {
    setBusy(true);
    setErr(null);
    const fd = new FormData();
    const fields: [string, string, string | null | undefined][] = [
      ['submitted_full_name', form.name.trim(), reg?.submitted_full_name],
      ['submitted_id_number', form.idn.trim(), reg?.submitted_id_number],
      ['submitted_address', form.addr.trim(), reg?.submitted_address],
      ['submitted_phone', form.phone.trim(), reg?.submitted_phone],
    ];
    for (const [k, v, old] of fields) {
      if (!v) continue; // trường trống: không gửi
      if (resubmit && v === (old ?? '')) continue; // bổ sung: chỉ gửi trường đã thay đổi
      fd.append(k, v);
    }
    ids.forEach((f) => fd.append('identity_documents', f));
    if (receipt) fd.append('deposit_receipt', receipt);
    try {
      if (resubmit) await api(`/registrations/${regId}`, { method: 'PUT', form: fd });
      else await api(`/sessions/${session.session_id}/registrations`, { method: 'POST', form: fd });
      nav('/my/registrations', { replace: true, state: { flash: resubmit ? 'Đã gửi bổ sung. Hồ sơ trở về trạng thái Chờ duyệt.' : 'Đã gửi hồ sơ. Hồ sơ ở trạng thái Chờ duyệt.' } });
    } catch (ex) {
      setErr(ex);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="wrap" style={{ maxWidth: 1000, margin: '0 auto' }}>
      <div className="h1">{resubmit ? 'Bổ sung hồ sơ đăng ký' : 'Nộp hồ sơ đăng ký tham gia đấu giá'}</div>
      <div className="mut" style={{ marginBottom: 14 }}>
        Phiên {session.code} · {session.asset_name} · Hạn nhận hồ sơ {dt(session.registration_deadline)}
      </div>
      {resubmit && (
        <div className="warn" style={{ marginBottom: 14 }}>
          <b>Lý do yêu cầu bổ sung:</b> {lastReason ?? '—'}
          <br />
          <b>Hạn bổ sung:</b> {dt(reg?.supplement_deadline)} · Chỉ cần gửi phần thay đổi hoặc tệp mới.
        </div>
      )}
      <div className="card" style={{ display: 'flex', gap: 40, justifyContent: 'center', marginBottom: 14, flexWrap: 'wrap' }}>
        <Step n={1} label="Thông tin người đăng ký" on={step >= 1} />
        <Step n={2} label="Giấy tờ & chứng từ" on={step >= 2} />
        <Step n={3} label="Kiểm tra & gửi" on={step >= 3} />
      </div>
      <div className="row">
        <div className="card col" style={{ flex: 1.4 }}>
          {step === 1 && (
            <div className="form">
              <div className="h2">Bước 1. Thông tin người đăng ký</div>
              <label>Họ và tên *<input className="in" value={form.name} onChange={(e) => setForm('name', e.target.value)} /></label>
              <label>Số CCCD/giấy tờ định danh *<input className="in" value={form.idn} onChange={(e) => setForm('idn', e.target.value.replace(/\s/g, ''))} /></label>
              <label>Địa chỉ<input className="in" value={form.addr} onChange={(e) => setForm('addr', e.target.value)} /></label>
              <label>Số điện thoại<input className="in" value={form.phone} onChange={(e) => setForm('phone', e.target.value)} /></label>
              {infoIssues.map((i) => <div key={i} className="errt">{i}</div>)}
              <div className="row" style={{ justifyContent: 'flex-end' }}>
                <button className="btn p" disabled={infoIssues.length > 0} onClick={() => setStep(2)}>Tiếp tục ›</button>
              </div>
            </div>
          )}
          {step === 2 && (
            <div className="form">
              <div className="h2">Bước 2. Giấy tờ theo quy chế</div>
              <div style={{ border: `1px dashed ${missingIds ? 'var(--seal)' : 'var(--line)'}`, borderRadius: 6, padding: 12 }}>
                <div style={{ fontWeight: 600 }}>Giấy tờ định danh (CCCD 2 mặt…) {!resubmit && <span style={{ color: 'var(--seal)' }}>*</span>}</div>
                <div className="mut">PDF, JPG, PNG; tối đa {MAX_MB} MB/tệp; chọn được nhiều tệp</div>
                <input type="file" multiple accept=".pdf,.jpg,.jpeg,.png" onChange={(e) => setIds(Array.from(e.target.files ?? []))} style={{ marginTop: 8 }} />
                {ids.map((f) => <div key={f.name} className="mut">✓ {f.name}</div>)}
                {missingIds && <div className="errt">Bắt buộc ít nhất một tệp.</div>}
              </div>
              <div style={{ border: '1px dashed var(--line)', borderRadius: 6, padding: 12 }}>
                <div style={{ fontWeight: 600 }}>Chứng từ nộp tiền đặt trước</div>
                <div className="mut">PDF, JPG, PNG; tối đa {MAX_MB} MB</div>
                <input type="file" accept=".pdf,.jpg,.jpeg,.png" onChange={(e) => setReceipt(e.target.files?.[0] ?? null)} style={{ marginTop: 8 }} />
              </div>
              {fileIssues.map((i) => <div key={i} className="errt">{i}</div>)}
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <button className="btn" onClick={() => setStep(1)}>‹ Quay lại</button>
                <button className="btn p" disabled={missingIds || fileIssues.length > 0} title={missingIds ? 'Còn thiếu giấy tờ bắt buộc' : undefined} onClick={() => setStep(3)}>Tiếp tục ›</button>
              </div>
            </div>
          )}
          {step === 3 && (
            <div className="form">
              <div className="h2">Bước 3. Kiểm tra & gửi</div>
              <table className="kv">
                <tbody>
                  <tr><td>Họ và tên</td><td>{form.name}</td></tr>
                  <tr><td>Số giấy tờ</td><td>{form.idn}</td></tr>
                  <tr><td>Địa chỉ</td><td>{form.addr || '—'}</td></tr>
                  <tr><td>Số điện thoại</td><td>{form.phone || '—'}</td></tr>
                  <tr><td>Giấy tờ định danh</td><td>{ids.map((f) => f.name).join(', ') || '—'}</td></tr>
                  <tr><td>Chứng từ tiền đặt trước</td><td>{receipt?.name ?? '—'}</td></tr>
                </tbody>
              </table>
              <ErrorBox error={err} />
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <button className="btn" onClick={() => setStep(2)}>‹ Quay lại</button>
                <button className="btn p lg" disabled={busy} onClick={submit}>{busy ? 'Đang gửi…' : resubmit ? 'Gửi bổ sung' : 'Gửi hồ sơ'}</button>
              </div>
            </div>
          )}
        </div>
        <div className="col" style={{ flex: 1 }}>
          <div className="warn"><b>Lưu ý:</b> Chứng từ bạn tải lên chỉ là căn cứ để nhân viên đối chiếu. Tiền đặt trước chỉ được ghi nhận sau khi nhân viên xác nhận.</div>
          <div className="card">
            <div className="h2">Sau khi gửi</div>
            <div style={{ lineHeight: 1.9, fontSize: 13 }}>
              • Hồ sơ chuyển sang <span className="b amber">Chờ duyệt</span><br />
              • Hệ thống lưu thời điểm nộp và bản thông tin đã gửi<br />
              • Mỗi người chỉ có <b>01 hồ sơ hiệu lực</b> trong một phiên<br />
              • Theo dõi kết quả tại <i>Hồ sơ của tôi</i>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
