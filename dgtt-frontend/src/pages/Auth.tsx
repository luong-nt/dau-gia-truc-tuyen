import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { api } from '../api/client';
import { homeFor, useAuth } from '../auth/AuthContext';
import { ErrorBox } from '../components/ui';

// SCR-03 – Đăng nhập (FR-02)
export function Login() {
  const { login } = useAuth();
  const nav = useNavigate();
  const [params] = useSearchParams();
  const [form, setForm] = useState({ login: '', password: '' });
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  return (
    <div className="wrap" style={{ maxWidth: 420, margin: '30px auto' }}>
      <form
        className="card form"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setErr(null);
          try {
            const u = await login(form.login.trim(), form.password);
            nav(params.get('next') || homeFor(u.role), { replace: true });
          } catch (ex) {
            setErr(ex);
          } finally {
            setBusy(false);
          }
        }}
      >
        <div className="h1">Đăng nhập</div>
        <label>
          Tên đăng nhập hoặc email
          <input className="in" autoFocus required value={form.login} onChange={(e) => setForm({ ...form, login: e.target.value })} />
        </label>
        <label>
          Mật khẩu
          <input className="in" type="password" required value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
        </label>
        <ErrorBox error={err} />
        <button className="btn p lg" disabled={busy}>{busy ? 'Đang đăng nhập…' : 'Đăng nhập'}</button>
        <div className="mut">Chưa có tài khoản? <Link to="/register">Đăng ký</Link></div>
      </form>
    </div>
  );
}

// SCR-03 – Đăng ký tài khoản Người tham gia (FR-01)
export function Register() {
  const { login } = useAuth();
  const nav = useNavigate();
  const [f, setF] = useState({ full_name: '', email: '', phone: '', username: '', password: '', confirm: '' });
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value });
  // Kiểm tra ngay tại giao diện (UI-04), khớp ràng buộc của backend
  const issues: string[] = [];
  if (f.username && !/^[A-Za-z0-9_.]{3,50}$/.test(f.username)) issues.push('Tên đăng nhập 3–50 ký tự, chỉ gồm chữ không dấu, số, "_" và "."');
  if (f.phone && !/^[0-9+]{9,15}$/.test(f.phone)) issues.push('Số điện thoại 9–15 chữ số');
  if (f.password && f.password.length < 8) issues.push('Mật khẩu tối thiểu 8 ký tự');
  if (f.confirm && f.confirm !== f.password) issues.push('Mật khẩu nhập lại không khớp');

  return (
    <div className="wrap" style={{ maxWidth: 520, margin: '20px auto' }}>
      <form
        className="card form"
        onSubmit={async (e) => {
          e.preventDefault();
          if (issues.length) return;
          setBusy(true);
          setErr(null);
          try {
            await api('/auth/register', {
              method: 'POST',
              body: {
                full_name: f.full_name.trim(),
                email: f.email.trim(),
                phone: f.phone.trim() || null,
                username: f.username.trim(),
                password: f.password,
              },
            });
            await login(f.username.trim(), f.password);
            nav('/', { replace: true });
          } catch (ex) {
            setErr(ex);
          } finally {
            setBusy(false);
          }
        }}
      >
        <div className="h1">Đăng ký tài khoản</div>
        <div className="mut">Tài khoản mới có vai trò Người tham gia đấu giá.</div>
        <label>Họ và tên *<input className="in" required value={f.full_name} onChange={set('full_name')} /></label>
        <label>Email *<input className="in" type="email" required value={f.email} onChange={set('email')} /></label>
        <label>Số điện thoại<input className="in" value={f.phone} onChange={set('phone')} /></label>
        <label>Tên đăng nhập *<input className="in" required value={f.username} onChange={set('username')} /></label>
        <label>Mật khẩu *<input className="in" type="password" required value={f.password} onChange={set('password')} /></label>
        <label>Nhập lại mật khẩu *<input className="in" type="password" required value={f.confirm} onChange={set('confirm')} /></label>
        {issues.map((i) => <div key={i} className="errt">{i}</div>)}
        <ErrorBox error={err} />
        <button className="btn p lg" disabled={busy || issues.length > 0}>{busy ? 'Đang tạo…' : 'Tạo tài khoản'}</button>
      </form>
    </div>
  );
}
