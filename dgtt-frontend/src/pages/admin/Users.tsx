import { useState } from 'react';
import { api } from '../../api/client';
import type { Page, Role, User } from '../../api/types';
import { Badge, ErrorBox, Loading, Pager, ReasonDialog, useLoad } from '../../components/ui';
import { dt, ROLE_LABEL } from '../../format';

// Quản lý tài khoản (FR-04) – Quản trị viên
export default function Users() {
  const [keyword, setKeyword] = useState('');
  const [q, setQ] = useState('');
  const [page, setPage] = useState(1);
  const list = useLoad(() => api<Page<User>>('/users', { query: { keyword: q, page, size: 20 } }), [q, page]);
  const [creating, setCreating] = useState(false);
  const [roleOf, setRoleOf] = useState<User | null>(null);
  const [newRole, setNewRole] = useState<Role>('STAFF');
  const [lockOf, setLockOf] = useState<User | null>(null);

  return (
    <>
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, flexDirection: 'row' }}>
        <div className="h1">Tài khoản</div>
        <button className="btn p" onClick={() => setCreating(true)}>+ Tạo tài khoản nội bộ</button>
      </div>
      <div className="card">
        <form className="row" style={{ gap: 8, marginBottom: 10, flexDirection: 'row' }} onSubmit={(e) => { e.preventDefault(); setPage(1); setQ(keyword.trim()); }}>
          <input className="in" placeholder="Tìm theo tên, tên đăng nhập, email…" value={keyword} onChange={(e) => setKeyword(e.target.value)} />
          <button className="btn">Tìm</button>
        </form>
        <ErrorBox error={list.error} />
        {list.loading && <Loading />}
        <div style={{ overflowX: 'auto' }}>
          <table>
            <thead><tr><th>ID</th><th>Họ tên</th><th>Tên đăng nhập</th><th>Email</th><th>Vai trò</th><th>Trạng thái</th><th>Tạo lúc</th><th></th></tr></thead>
            <tbody>
              {list.data?.items.map((u) => (
                <tr key={u.user_id}>
                  <td>{u.user_id}</td>
                  <td>{u.full_name}</td>
                  <td>{u.username}</td>
                  <td>{u.email}</td>
                  <td>{ROLE_LABEL[u.role]}</td>
                  <td>{u.status === 'ACTIVE' ? <Badge color="green">Hoạt động</Badge> : <Badge color="red">Đã khóa</Badge>}</td>
                  <td className="mut">{dt(u.created_at)}</td>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    <button className="btn" onClick={() => { setRoleOf(u); setNewRole(u.role); }}>Đổi vai trò</button>{' '}
                    <button className={`btn ${u.status === 'ACTIVE' ? 'r' : ''}`} onClick={() => setLockOf(u)}>{u.status === 'ACTIVE' ? 'Khóa' : 'Mở khóa'}</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {list.data && <Pager page={list.data.page} size={list.data.size} total={list.data.total} onPage={setPage} />}
      </div>

      {creating && <CreateUser onClose={() => setCreating(false)} onDone={list.reload} />}
      {roleOf && (
        <ReasonDialog
          title={`Đổi vai trò: ${roleOf.full_name}`}
          requireReason
          confirmText="Lưu"
          extra={<label>Vai trò mới<select className="in" value={newRole} onChange={(e) => setNewRole(e.target.value as Role)}>{Object.entries(ROLE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>}
          onConfirm={async (reason) => { await api(`/users/${roleOf.user_id}/role`, { method: 'PATCH', body: { role: newRole, reason } }); await list.reload(); }}
          onClose={() => setRoleOf(null)}
        />
      )}
      {lockOf && (
        <ReasonDialog
          title={`${lockOf.status === 'ACTIVE' ? 'Khóa' : 'Mở khóa'} tài khoản ${lockOf.username}`}
          requireReason
          danger={lockOf.status === 'ACTIVE'}
          confirmText={lockOf.status === 'ACTIVE' ? 'Khóa tài khoản' : 'Mở khóa'}
          onConfirm={async (reason) => { await api(`/users/${lockOf.user_id}/status`, { method: 'PATCH', body: { status: lockOf.status === 'ACTIVE' ? 'LOCKED' : 'ACTIVE', reason } }); await list.reload(); }}
          onClose={() => setLockOf(null)}
        />
      )}
    </>
  );
}

function CreateUser({ onClose, onDone }: { onClose: () => void; onDone: () => Promise<void> }) {
  const [f, setF] = useState({ role: 'STAFF' as Role, full_name: '', email: '', phone: '', username: '', password: '' });
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.value });
  return (
    <div className="dialog-bg" onClick={onClose}>
      <form
        className="dialog form"
        onClick={(e) => e.stopPropagation()}
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setErr(null);
          try {
            await api('/users', { method: 'POST', body: { ...f, phone: f.phone || null } });
            await onDone();
            onClose();
          } catch (ex) {
            setErr(ex);
          } finally {
            setBusy(false);
          }
        }}
      >
        <div className="h2">Tạo tài khoản nội bộ</div>
        <label>Vai trò<select className="in" value={f.role} onChange={set('role')}>{(['STAFF', 'AUCTIONEER', 'ADMIN'] as Role[]).map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}</select></label>
        <label>Họ và tên *<input className="in" required value={f.full_name} onChange={set('full_name')} /></label>
        <label>Email *<input className="in" type="email" required value={f.email} onChange={set('email')} /></label>
        <label>Số điện thoại<input className="in" value={f.phone} onChange={set('phone')} /></label>
        <label>Tên đăng nhập *<input className="in" required pattern="[A-Za-z0-9_.]{3,50}" value={f.username} onChange={set('username')} /></label>
        <label>Mật khẩu tạm (≥ 8 ký tự) *<input className="in" type="password" required minLength={8} value={f.password} onChange={set('password')} /></label>
        <ErrorBox error={err} />
        <div className="row" style={{ justifyContent: 'flex-end', gap: 8, flexDirection: 'row' }}>
          <button type="button" className="btn" onClick={onClose}>Hủy</button>
          <button className="btn p" disabled={busy}>Tạo</button>
        </div>
      </form>
    </div>
  );
}
