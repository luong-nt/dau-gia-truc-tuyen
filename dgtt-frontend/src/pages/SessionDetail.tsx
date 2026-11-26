import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api, ApiError, downloadFile } from '../api/client';
import type { AssetDetail, OfficialResult, Page, Registration, Session } from '../api/types';
import { useAuth } from '../auth/AuthContext';
import { AssetImage, firstImage } from '../components/AssetImage';
import { Badge, ErrorBox, Loading, useLoad } from '../components/ui';
import { dt, fileSize, parseUtc, REG_STATUS, SESSION_STATUS, vnd } from '../format';

/** Ảnh và tài liệu của tài sản (FR-07). Tài sản chưa công khai thì khách không xem được: chỉ hiện ô trống. */
function AssetGallery({ asset }: { asset: AssetDetail | null }) {
  const [current, setCurrent] = useState<number | null>(null);
  if (!asset) return <div className="img" style={{ height: 280 }}>Chưa có ảnh tài sản</div>;
  const images = asset.attachments.filter((a) => a.file_type === 'ASSET_IMAGE');
  const docs = asset.attachments.filter((a) => a.file_type === 'ASSET_DOCUMENT');
  const main = images.find((a) => a.attachment_id === current) ?? firstImage(asset.attachments);
  return (
    <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
      <AssetImage assetId={asset.asset_id} att={main} height={280} alt={asset.name} />
      {images.length > 1 && (
        <div style={{ display: 'flex', gap: 6, padding: 8, overflowX: 'auto' }}>
          {images.map((im) => (
            <div
              key={im.attachment_id}
              onClick={() => setCurrent(im.attachment_id)}
              style={{ width: 72, flex: '0 0 72px', cursor: 'pointer', outline: main?.attachment_id === im.attachment_id ? '2px solid #1d4ed8' : 'none', borderRadius: 4, overflow: 'hidden' }}
            >
              <AssetImage assetId={asset.asset_id} att={im} height={52} />
            </div>
          ))}
        </div>
      )}
      {(asset.description || docs.length > 0) && (
        <div style={{ padding: '10px 14px' }}>
          {asset.description && <div style={{ whiteSpace: 'pre-wrap', fontSize: 13.5, lineHeight: 1.6, marginBottom: 8 }}>{asset.description}</div>}
          {docs.map((d) => (
            <div key={d.attachment_id} style={{ fontSize: 13 }}>
              <a href="#" onClick={(e) => { e.preventDefault(); downloadFile(`/assets/${asset.asset_id}/attachments/${d.attachment_id}`, undefined, d.file_name); }}>
                Tài liệu: {d.file_name}
              </a>{' '}
              <span className="mut">{fileSize(d.file_size)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/** Kết quả chính thức sau khi Đấu giá viên xác nhận (FR-23). Không công bố người trúng trước khi xác nhận. */
function OfficialResultCard({ sid }: { sid: number }) {
  const { data, error, loading } = useLoad(async () => {
    try {
      return await api<OfficialResult>(`/sessions/${sid}/results/official`);
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) return null;
      throw e;
    }
  }, [sid]);
  if (loading) return null;
  if (error) return <div className="card"><div className="h2">Kết quả phiên</div><ErrorBox error={error} /></div>;
  if (!data)
    return (
      <div className="card">
        <div className="h2">Kết quả phiên</div>
        <div className="mut">Phiên đã kết thúc. Kết quả đang chờ Đấu giá viên xác nhận.</div>
      </div>
    );
  return (
    <div className="card" style={{ border: data.is_mine ? '2px solid #15803d' : undefined }}>
      <div className="h2">Kết quả chính thức</div>
      {data.is_mine && <div className="ok-box" style={{ marginBottom: 10 }}>Bạn ({data.my_alias}) là người trúng đấu giá.</div>}
      {data.is_failed ? (
        <div>Đấu giá không thành: không có lượt trả giá hợp lệ.</div>
      ) : (
        <table className="kv"><tbody>
          <tr><td>Người trúng đấu giá</td><td><b>{data.winning_bidder_alias}</b></td></tr>
          <tr><td>Giá trúng</td><td><b style={{ color: '#15803d' }}>{vnd(data.winning_amount)}</b></td></tr>
        </tbody></table>
      )}
      <div className="mut" style={{ marginTop: 6 }}>Xác nhận lúc {dt(data.confirmed_at)} · phiên bản {data.version_no}</div>
      <button
        className="btn"
        style={{ marginTop: 10 }}
        onClick={() => downloadFile(`/sessions/${sid}/results/${data.result_id}/minutes`, undefined, `bien-ban-${data.session_code}.pdf`)}
      >
        Tải biên bản kết quả (PDF)
      </button>
    </div>
  );
}

// SCR-02 – Chi tiết tài sản và thông báo (FR-07, FR-08, FR-09)
export default function SessionDetail() {
  const { id } = useParams();
  const sid = Number(id);
  const { user } = useAuth();
  const nav = useNavigate();
  const { data: s, error, loading } = useLoad(() => api<Session>(`/sessions/${sid}`), [sid, user?.user_id]);
  const { data: asset } = useLoad(
    async () => (s ? await api<AssetDetail>(`/assets/${s.asset_id}`).catch(() => null) : null),
    [s?.asset_id, user?.user_id],
  );
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
          <AssetGallery asset={asset} />
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
          {s.status === 'ENDED' && user && (user.role !== 'BIDDER' || mine?.status === 'APPROVED') && <OfficialResultCard sid={sid} />}
        </div>
      </div>
    </div>
  );
}
