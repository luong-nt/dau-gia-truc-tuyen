import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api } from '../../api/client';
import type { Page, Session, SessionStatus } from '../../api/types';
import { useAuth } from '../../auth/AuthContext';
import { Badge, ErrorBox, Loading, Pager, useLoad } from '../../components/ui';
import { dt, fromLocalInput, money, SESSION_STATUS, toLocalInput, vnd } from '../../format';

// Danh sách phiên cho Nhân viên / Đấu giá viên / Quản trị viên (FR-16, FR-17)
export function SessionList() {
  const { user } = useAuth();
  const [status, setStatus] = useState<SessionStatus | ''>('');
  const [keyword, setKeyword] = useState('');
  const [q, setQ] = useState('');
  const [page, setPage] = useState(1);
  const { data, error, loading } = useLoad(
    () => api<Page<Session>>('/sessions/manage', { query: { status, keyword: q, page, size: 20 } }),
    [status, q, page],
  );
  return (
    <>
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, flexDirection: 'row' }}>
        <div>
          <div className="h1">Phiên đấu giá</div>
          <div className="mut">{user?.role === 'AUCTIONEER' ? 'Các phiên được phân công cho bạn' : `${data?.total ?? 0} phiên`}</div>
        </div>
        {user?.role === 'STAFF' && <Link className="btn p" to="/manage/sessions/new">+ Tạo phiên</Link>}
      </div>
      <div className="card">
        <form className="row" style={{ gap: 8, marginBottom: 10, flexDirection: 'row' }} onSubmit={(e) => { e.preventDefault(); setPage(1); setQ(keyword.trim()); }}>
          <input className="in" style={{ flex: 2 }} placeholder="Tìm theo mã phiên, tên tài sản…" value={keyword} onChange={(e) => setKeyword(e.target.value)} />
          <select className="in" style={{ flex: 1 }} value={status} onChange={(e) => { setStatus(e.target.value as SessionStatus | ''); setPage(1); }}>
            <option value="">Tất cả trạng thái</option>
            {Object.entries(SESSION_STATUS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
          </select>
          <button className="btn">Lọc</button>
        </form>
        <ErrorBox error={error} />
        {loading && <Loading />}
        <div style={{ overflowX: 'auto' }}>
          <table>
            <thead><tr><th>Mã phiên</th><th>Tài sản</th><th>Giá khởi điểm</th><th>Thời gian tổ chức</th><th>Trạng thái</th></tr></thead>
            <tbody>
              {data?.items.map((s) => (
                <tr key={s.session_id}>
                  <td><Link to={`/manage/sessions/${s.session_id}`}><b>{s.code}</b></Link></td>
                  <td>{s.asset_code} · {s.asset_name}</td>
                  <td>{vnd(s.starting_price)}</td>
                  <td>{dt(s.start_time)}</td>
                  <td><Badge color={SESSION_STATUS[s.status].color}>{SESSION_STATUS[s.status].label}</Badge></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {data && data.items.length === 0 && <div className="mut" style={{ padding: 10 }}>Không có phiên nào.</div>}
        {data && <Pager page={data.page} size={data.size} total={data.total} onPage={setPage} />}
      </div>
    </>
  );
}

// Tạo / sửa phiên (FR-16). Tài sản và đấu giá viên nhập theo mã số vì API tài sản (TASK-007) chưa có.
export function SessionForm() {
  const { id } = useParams();
  const editing = Boolean(id);
  const nav = useNavigate();
  const { data: existing, loading, error } = useLoad(() => (editing ? api<Session>(`/sessions/${id}`) : Promise.resolve(null)), [id]);
  const [f, setF] = useState<Record<string, string> | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  if (loading) return <Loading />;
  if (error) return <ErrorBox error={error} />;
  const form = f ?? {
    asset_id: existing ? String(existing.asset_id) : '',
    auctioneer_id: existing ? String(existing.auctioneer_id) : '',
    starting_price: existing ? String(money(existing.starting_price)) : '',
    bid_increment: existing ? String(money(existing.bid_increment)) : '',
    deposit_amount: existing ? String(money(existing.deposit_amount)) : '',
    registration_deadline: toLocalInput(existing?.registration_deadline),
    deposit_deadline: toLocalInput(existing?.deposit_deadline),
    start_time: toLocalInput(existing?.start_time),
    end_time: toLocalInput(existing?.end_time),
    notice_content: existing?.notice_content ?? '',
    reason: '',
  };
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setF({ ...form, [k]: e.target.value });
  const published = existing && existing.status !== 'DRAFT';
  const issues: string[] = [];
  const t = (k: string) => (form[k] ? new Date(fromLocalInput(form[k])).getTime() : NaN);
  if (form.registration_deadline && form.start_time && t('registration_deadline') >= t('start_time')) issues.push('Hạn nhận hồ sơ phải trước giờ bắt đầu');
  if (form.deposit_deadline && form.start_time && t('deposit_deadline') > t('start_time')) issues.push('Hạn nộp tiền đặt trước không được sau giờ bắt đầu');
  if (form.start_time && form.end_time && t('start_time') >= t('end_time')) issues.push('Giờ kết thúc phải sau giờ bắt đầu');
  if (published && !form.reason.trim()) issues.push('Phiên đã công khai: cần nhập lý do thay đổi');

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    const body: Record<string, unknown> = {
      auctioneer_id: Number(form.auctioneer_id),
      starting_price: Number(form.starting_price),
      bid_increment: Number(form.bid_increment),
      deposit_amount: Number(form.deposit_amount || 0),
      registration_deadline: fromLocalInput(form.registration_deadline),
      deposit_deadline: fromLocalInput(form.deposit_deadline),
      start_time: fromLocalInput(form.start_time),
      end_time: fromLocalInput(form.end_time),
      notice_content: form.notice_content || null,
    };
    if (form.reason.trim()) body.reason = form.reason.trim();
    try {
      const out = editing
        ? await api<Session>(`/sessions/${id}`, { method: 'PUT', body })
        : await api<Session>('/sessions', { method: 'POST', body: { ...body, asset_id: Number(form.asset_id) } });
      nav(`/manage/sessions/${out.session_id}`);
    } catch (ex) {
      setErr(ex);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="card form" style={{ maxWidth: 760 }} onSubmit={submit}>
      <div className="h1">{editing ? `Sửa phiên ${existing?.code}` : 'Tạo phiên đấu giá'}</div>
      <div className="row" style={{ flexDirection: 'row', gap: 12 }}>
        <label style={{ flex: 1 }}>Mã số tài sản *<input className="in" type="number" min={1} required disabled={editing} value={form.asset_id} onChange={set('asset_id')} /></label>
        <label style={{ flex: 1 }}>Mã số đấu giá viên *<input className="in" type="number" min={1} required value={form.auctioneer_id} onChange={set('auctioneer_id')} /></label>
      </div>
      <div className="note">Chọn tài sản từ danh sách sẽ có khi backend xong API tài sản (TASK-007). Tạm thời nhập mã số (ID).</div>
      <div className="row" style={{ flexDirection: 'row', gap: 12 }}>
        <label style={{ flex: 1 }}>Giá khởi điểm (đ) *<input className="in" type="number" min={1} required value={form.starting_price} onChange={set('starting_price')} /></label>
        <label style={{ flex: 1 }}>Bước giá (đ) *<input className="in" type="number" min={1} required value={form.bid_increment} onChange={set('bid_increment')} /></label>
        <label style={{ flex: 1 }}>Tiền đặt trước (đ) *<input className="in" type="number" min={0} required value={form.deposit_amount} onChange={set('deposit_amount')} /></label>
      </div>
      <div className="row" style={{ flexDirection: 'row', gap: 12 }}>
        <label style={{ flex: 1 }}>Hạn nhận hồ sơ (GMT+7) *<input className="in" type="datetime-local" required value={form.registration_deadline} onChange={set('registration_deadline')} /></label>
        <label style={{ flex: 1 }}>Hạn nộp tiền đặt trước *<input className="in" type="datetime-local" required value={form.deposit_deadline} onChange={set('deposit_deadline')} /></label>
      </div>
      <div className="row" style={{ flexDirection: 'row', gap: 12 }}>
        <label style={{ flex: 1 }}>Bắt đầu *<input className="in" type="datetime-local" required value={form.start_time} onChange={set('start_time')} /></label>
        <label style={{ flex: 1 }}>Kết thúc *<input className="in" type="datetime-local" required value={form.end_time} onChange={set('end_time')} /></label>
      </div>
      <label>Nội dung thông báo đấu giá<textarea className="in" style={{ minHeight: 120 }} value={form.notice_content} onChange={set('notice_content')} /></label>
      {published && <label>Lý do thay đổi *<input className="in" value={form.reason} onChange={set('reason')} /></label>}
      {issues.map((i) => <div key={i} className="errt">{i}</div>)}
      <ErrorBox error={err} />
      <div className="row" style={{ justifyContent: 'flex-end', gap: 8, flexDirection: 'row' }}>
        <button type="button" className="btn" onClick={() => nav(-1)}>Hủy</button>
        <button className="btn p" disabled={busy || issues.length > 0}>{busy ? 'Đang lưu…' : 'Lưu'}</button>
      </div>
    </form>
  );
}
