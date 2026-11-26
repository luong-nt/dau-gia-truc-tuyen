import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { ROLE_LABEL } from '../format';

function Logo({ sub }: { sub: string }) {
  return (
    <NavLink to="/" className="logo" style={{ textDecoration: 'none' }}>
      DGTT<small>{sub}</small>
    </NavLink>
  );
}

function AccountArea() {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  if (!user)
    return (
      <>
        <NavLink className="btn" to="/login">Đăng nhập</NavLink>
        <NavLink className="btn p" to="/register">Đăng ký tài khoản</NavLink>
      </>
    );
  return (
    <>
      {user.role !== 'BIDDER' && (
        <NavLink className="btn" to={user.role === 'ADMIN' ? '/admin/users' : '/manage/sessions'}>
          Trang quản lý
        </NavLink>
      )}
      <NavLink className="btn" to="/me" title={ROLE_LABEL[user.role]}>
        {user.full_name}
      </NavLink>
      <button
        className="btn"
        onClick={async () => {
          await logout();
          nav('/');
        }}
      >
        Đăng xuất
      </button>
    </>
  );
}

function ExpiredBanner() {
  const { sessionExpired, clearExpired } = useAuth();
  const nav = useNavigate();
  if (!sessionExpired) return null;
  return (
    <div className="warn" style={{ borderRadius: 0, display: 'flex', gap: 12, alignItems: 'center' }}>
      Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại; thao tác trước đó không được gửi lại tự động.
      <button className="btn" onClick={() => { clearExpired(); nav('/login'); }}>Đăng nhập lại</button>
    </div>
  );
}

/** Khu công khai và người tham gia: thanh điều hướng ngang. */
export function PublicLayout() {
  const { user } = useAuth();
  return (
    <>
      <div className="top">
        <Logo sub="Đấu giá trực tuyến" />
        <div className="nav">
          <NavLink to="/" end>Trang chủ</NavLink>
          {user?.role === 'BIDDER' && <NavLink to="/my/registrations">Hồ sơ của tôi</NavLink>}
        </div>
        <div className="sp" />
        <AccountArea />
      </div>
      <ExpiredBanner />
      <Outlet />
    </>
  );
}

/** Khu quản lý: menu dọc theo vai trò. */
export function ManageLayout() {
  const { user } = useAuth();
  const role = user?.role;
  return (
    <>
      <div className="top">
        <Logo sub="Trang quản lý" />
        <div className="sp" />
        <AccountArea />
      </div>
      <ExpiredBanner />
      <div className="shell">
        <nav className="side">
          <div className="sec">Nghiệp vụ</div>
          {(role === 'STAFF' || role === 'AUCTIONEER' || role === 'ADMIN') && (
            <NavLink to="/manage/sessions">Phiên đấu giá</NavLink>
          )}
          {role === 'STAFF' && <NavLink to="/manage/registrations">Xét duyệt hồ sơ</NavLink>}
          {role === 'STAFF' && <NavLink to="/manage/assets">Tài sản</NavLink>}
          {(role === 'STAFF' || role === 'ADMIN') && <NavLink to="/manage/reports">Thống kê, báo cáo</NavLink>}
          {role === 'ADMIN' && (
            <>
              <div className="sec">Quản trị</div>
              <NavLink to="/admin/users">Tài khoản</NavLink>
            </>
          )}
        </nav>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </>
  );
}
