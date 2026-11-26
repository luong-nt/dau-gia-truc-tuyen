import { Link, useNavigate, useParams } from 'react-router-dom';
import { api } from '../api/client';
import type { Page, Registration, Session } from '../api/types';
import { useAuth } from '../auth/AuthContext';
import { Badge, ErrorBox, Loading, useLoad } from '../components/ui';
import { dt, parseUtc, REG_STATUS, SESSION_STATUS, vnd } from '../format';

// SCR-02 – Chi tiết tài sản và thông báo (FR-07, FR-08, FR-09)
export default function SessionDetail() {
  const { id } = useParams();
  const sid = Number(id);
  const { user } = useAuth();
  const nav = useNavigate();
  const { data: s, error, loading } = useLoad(() => api<Session>(`/sessions/${sid}`), [sid, user?.user_id]);
  const { data: mine } = useLoad(
    async () => {
      if (user?.role !== 'BIDDER') return null;
      const page = await api<Page<Registration>>('/registrations/me', { query: { size: 100 } });
      return page.items.find((r) => r.session_id === sid) ?? null;
    },
    [sid, user?.user_id],
  );

  if (loading) return <Loading />;
  if (error || !s) return <div className="wrap"><ErrorBox error={error ?? 'Không tìm thấy phiên'} /></div>;

  const st = SESSION_STATUS[s.status];
  const deadline = parseUtc(s.registration_deadline);
  const open = s.status === 'OPEN_FOR_REGISTRATION' && deadline !== null && deadline.getTime() > Date.now();
  const roomOpen = ['UPCOMING', 'IN_PROGRESS', 'PAUSED', 'ENDED'].includes(s.status);

  let action;
  if (user && user.role !== 'BIDDER') {
    action = <Link className="btn" to={`/manage/sessions/${sid}`}>Mở trang quản lý phiên</Link>;
  } else if (mine) {
    action = (
      <div className="col">
        <div>
          Hồ sơ của bạn: <Badge color={REG_STATUS[mine.status].color}>{REG_STATUS[mine.status].label}</Badge>
          {mine.bidder_alias && <> · Mã tham gia <b>{mine.bidder_alias}</b></>}
        </div>
        {mine.status === 'APPROVED' && roomOpen ? (
          <Link className="btn g lg" style={{ textAlign: 'center' }} to={`/room/${sid}`}>Vào phòng đấu giá</Link>
        ) : (
          <Link className="btn" style={{ textAlign: 'center' }} to="/my/registrations">Xem hồ sơ của tôi</Link>
        )}
      </div>
    );
  } else if (open) {
    action = (
      <button
        className="btn p lg"
        style={{ width: '100%' }}
        onClick={() => nav(user ? `/sessions/${sid}/register` : `/login?next=/sessions/${sid}/register`)}
      >
        Nộp hồ sơ đăng ký tham gia
      </button>
    );
  } else {
    action = <div className="mut">Phiên không còn nhận hồ sơ.</div>;
  }

  return (
    <div className="wrap">
      <div className="mut" style={{ marginBottom: 8 }}>
        <Link to="/">Trang chủ</Link> › {s.asset_code} · {s.code}
      </div>
      <div className="row">
        <div className="col" style={{ flex: 1.1 }}>
          <div className="img" style={{ height: 280 }}>Ảnh tài sản (chờ API tài sản)</div>
          <div className="card">
            <div className="h2">Thông báo đấu giá</div>
            <div style={{ whiteSpace: 'pre-wrap', fontSize: 13.5, lineHeight: 1.6 }}>
              {s.notice_content || <span className="mut">Chưa có nội dung thông báo.</span>}
            </div>
          </div>
        </div>
        <div className="col" style={{ flex: 1 }}>
          <div className="card">
            <Badge color={st.color}>{st.label}</Badge>
            <div className="h1" style={{ marginTop: 8 }}>{s.asset_name}</div>
            <div className="mut">Mã tài sản: {s.asset_code} · Mã phiên: {s.code}</div>
            <table className="kv" style={{ marginTop: 12 }}>
              <tbody>
                <tr><td>Giá khởi điểm</td><td><b>{vnd(s.starting_price)}</b></td></tr>
                <tr><td>Bước giá</td><td><b>{vnd(s.bid_increment)}</b></td></tr>
                <tr><td>Tiền đặt trước</td><td><b>{vnd(s.deposit_amount)}</b></td></tr>
                <tr><td>Hạn nhận hồ sơ</td><td><b>{dt(s.registration_deadline)}</b></td></tr>
                <tr><td>Hạn nộp tiền đặt trước</td><td><b>{dt(s.deposit_deadline)}</b></td></tr>
                <tr><td>Thời gian tổ chức</td><td><b>{dt(s.start_time)} – {dt(s.end_time)}</b></td></tr>
                <tr><td>Hình thức</td><td><b>Trả giá lên, trực tuyến</b></td></tr>
              </tbody>
            </table>
          </div>
          <div className="card">
            <div className="h2">Đăng ký tham gia phiên</div>
            <div className="mut" style={{ marginBottom: 10, fontSize: 13 }}>
              Có tài khoản chưa đồng nghĩa đủ điều kiện trả giá. Bạn cần nộp hồ sơ, được nhân viên xét duyệt và xác
              nhận tiền đặt trước.
            </div>
            {action}
          </div>
        </div>
      </div>
    </div>
  );
}
