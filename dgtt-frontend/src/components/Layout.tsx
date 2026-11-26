import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { ROLE_LABEL } from '../format';

/** Dấu búa đấu giá – dùng chung cho thanh trên và phòng đấu giá. */
export function GavelMark() {
  return (
    <span className="mark" aria-hidden="true">
      <svg viewBox="0 0 20 20">
        <g transform="rotate(-45 10 9)">
          <rect x="5" y="3.2" width="10" height="5" rx="1.3" fill="#fff" />
          <rect x="9.1" y="8" width="1.8" height="9.5" rx=".9" fill="#fff" />
        </g>
        <rect x="2" y="16.6" width="8.5" height="2" rx="1" fill="#3FB3A3" />
      </svg>
    </span>
  );
}

function Logo({ sub }: { sub: string }) {
  return (
    <NavLink to="/" className="logo">
      <GavelMark />
      <span>DGTT<small>{sub}</small></span>
    </NavLink>
  );
}

function Footer() {
  return (
    <footer className="foot">
      <div className="foot-in">
        <span>DGTT – Hệ thống đấu giá trực tuyến. Đồ án môn Công nghệ phần mềm.</span>
        <span>Giờ hiển thị theo GMT+7, đồng bộ với giờ máy chủ.</span>
      </div>
    </footer>
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
      <Footer />
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
