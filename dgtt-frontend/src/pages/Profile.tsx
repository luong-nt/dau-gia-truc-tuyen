import { useState } from 'react';
import { api } from '../api/client';
import type { User } from '../api/types';
import { useAuth } from '../auth/AuthContext';
import { ErrorBox } from '../components/ui';
import { ROLE_LABEL } from '../format';

// SCR-05 (phần thông tin cá nhân) – FR-02, FR-03
export default function Profile() {
  const { user, refresh } = useAuth();
  const [f, setF] = useState({ full_name: user?.full_name ?? '', email: user?.email ?? '', phone: user?.phone ?? '' });
  const [pw, setPw] = useState({ current_password: '', new_password: '' });
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const [msg2, setMsg2] = useState<string | null>(null);
  const [err2, setErr2] = useState<unknown>(null);
  if (!user) return null;
  return (
    <div className="wrap" style={{ maxWidth: 960, margin: '0 auto' }}>
      <div className="h1">Trang cá nhân</div>
      <div className="mut" style={{ marginBottom: 14 }}>
        {user.username} · {ROLE_LABEL[user.role]}
      </div>
      <div className="row">
        <form
          className="card form"
          style={{ flex: 1 }}
          onSubmit={async (e) => {
            e.preventDefault();
            setErr(null);
            setMsg(null);
            try {
              await api<User>('/auth/me', {
                method: 'PUT',
                body: { full_name: f.full_name.trim(), email: f.email.trim(), phone: f.phone.trim() || null },
              });
              await refresh();
              setMsg('Đã cập nhật thông tin. Hồ sơ đã nộp trước đây không thay đổi.');
            } catch (ex) {
              setErr(ex);
            }
          }}
        >
          <div className="h2">Thông tin cá nhân</div>
          <label>Họ và tên<input className="in" value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} /></label>
          <label>Email<input className="in" type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></label>
          <label>Số điện thoại<input className="in" value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} /></label>
          <ErrorBox error={err} />
          {msg && <div className="ok-box">{msg}</div>}
          <button className="btn p">Lưu thay đổi</button>
        </form>
        <form
          className="card form"
          style={{ flex: 1 }}
          onSubmit={async (e) => {
            e.preventDefault();
            setErr2(null);
            setMsg2(null);
            try {
              await api('/auth/change-password', { method: 'POST', body: pw });
              setPw({ current_password: '', new_password: '' });
              setMsg2('Đã đổi mật khẩu.');
            } catch (ex) {
              setErr2(ex);
            }
          }}
        >
          <div className="h2">Đổi mật khẩu</div>
          <label>Mật khẩu hiện tại<input className="in" type="password" required value={pw.current_password} onChange={(e) => setPw({ ...pw, current_password: e.target.value })} /></label>
          <label>Mật khẩu mới (tối thiểu 8 ký tự)<input className="in" type="password" required minLength={8} value={pw.new_password} onChange={(e) => setPw({ ...pw, new_password: e.target.value })} /></label>
          <ErrorBox error={err2} />
          {msg2 && <div className="ok-box">{msg2}</div>}
          <button className="btn p">Đổi mật khẩu</button>
        </form>
      </div>
    </div>
  );
}
