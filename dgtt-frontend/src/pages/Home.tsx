import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';
import type { AssetDetail, Page, Session, SessionStatus } from '../api/types';
import { AssetImage, firstImage } from '../components/AssetImage';
import { Badge, ErrorBox, Loading, Pager, useLoad } from '../components/ui';
import { countdown, dt, parseUtc, SESSION_STATUS, vnd } from '../format';

// SCR-01 – Trang chủ và tra cứu tài sản (FR-07, FR-09)
const FILTERS: (SessionStatus | '')[] = ['', 'OPEN_FOR_REGISTRATION', 'UPCOMING', 'IN_PROGRESS', 'ENDED'];

function keyTime(s: Session) {
  switch (s.status) {
    case 'OPEN_FOR_REGISTRATION':
      return `Hạn hồ sơ: ${dt(s.registration_deadline)}`;
    case 'IN_PROGRESS':
    case 'PAUSED':
      return `Kết thúc: ${dt(s.end_time)}`;
    default:
      return `Tổ chức: ${dt(s.start_time)}`;
  }
}

/** Ảnh đầu tiên của tài sản trên thẻ phiên (FR-07). */
function CardImage({ assetId, height = 168 }: { assetId: number; height?: number }) {
  const { data } = useLoad(() => api<AssetDetail>(`/assets/${assetId}`).catch(() => null), [assetId]);
  return <AssetImage assetId={assetId} att={firstImage(data?.attachments)} height={height} />;
}

const isLive = (s: Session) => s.status === 'IN_PROGRESS';

/** Đồng hồ đếm ngược hiển thị trên trang chủ (tham khảo; giờ chính xác xem trong phòng đấu giá). */
function useTick() {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, []);
  return now;
}

function LiveFeature({ s }: { s: Session }) {
  const now = useTick();
  const end = parseUtc(s.end_time)?.getTime() ?? 0;
  return (
    <Link to={`/sessions/${s.session_id}`} className="live" style={{ textDecoration: 'none' }}>
      <div className="live-img"><CardImage assetId={s.asset_id} height={230} /></div>
      <div className="live-body">
        <div><span className="b livechip">Đang diễn ra</span></div>
        <div className="live-name">{s.asset_name}</div>
        <div className="live-k">Giá khởi điểm</div>
        <div className="live-v">{vnd(s.starting_price)}</div>
        <div className="live-k">Thời gian còn lại</div>
        <div className="live-v">{countdown(end - now)}</div>
        <div className="live-cta">Xem phiên {s.code}</div>
      </div>
    </Link>
  );
}

export default function Home() {
  const [status, setStatus] = useState<SessionStatus | ''>('');
  const [keyword, setKeyword] = useState('');
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const { data, error, loading } = useLoad(
    () => api<Page<Session>>('/sessions', { query: { status, keyword: query, page, size: 12 } }),
    [status, query, page],
  );
  const { data: live } = useLoad(
    () => api<Page<Session>>('/sessions', { query: { status: 'IN_PROGRESS', page: 1, size: 1 } }).catch(() => null),
    [],
  );
  const featured = live?.items[0];

  return (
    <>
      <section className="hero">
        <div className="hero-in">
          <div>
            <h1>Tìm kiếm tài sản đấu giá</h1>
            <p>Thông tin công khai theo thông báo đấu giá. Giờ hiển thị theo GMT+7.</p>
            <form
              className="search"
              role="search"
              onSubmit={(e) => {
                e.preventDefault();
                setPage(1);
                setQuery(keyword.trim());
              }}
            >
              <input
                aria-label="Tìm theo tên tài sản hoặc mã phiên"
                placeholder="Nhập tên tài sản hoặc mã phiên…"
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
              />
              <button className="btn p">Tìm kiếm</button>
            </form>
          </div>
          {featured ? <LiveFeature s={featured} /> : <div className="live-empty">Hiện chưa có phiên nào đang diễn ra. Các phiên sắp tới được liệt kê bên dưới.</div>}
        </div>
      </section>
      <div className="wrap">
        <div className="tabs">
          {FILTERS.map((f) => (
            <button
              key={f || 'all'}
              className={`btn ${status === f ? 'p' : ''}`}
              onClick={() => {
                setStatus(f);
                setPage(1);
              }}
            >
              {f ? SESSION_STATUS[f].label : 'Tất cả'}
            </button>
          ))}
        </div>
        <ErrorBox error={error} />
        {loading && <Loading />}
        {data && data.items.length === 0 && <div className="card mut">Không có phiên nào phù hợp.</div>}
        <div className="grid3">
          {data?.items.map((s) => (
            <Link key={s.session_id} to={`/sessions/${s.session_id}`} className="scard">
              <div className="scard-img">
                <CardImage assetId={s.asset_id} />
                {isLive(s) ? <span className="b livechip">{SESSION_STATUS[s.status].label}</span> : <Badge color={SESSION_STATUS[s.status].color}>{SESSION_STATUS[s.status].label}</Badge>}
              </div>
              <div className="scard-body">
                <span className="scard-code">{s.asset_code} · {s.code}</span>
                <div className="scard-name">{s.asset_name}</div>
                <div className="facts">
                  <div><span>Giá khởi điểm</span><b className="price">{vnd(s.starting_price)}</b></div>
                  <div><span>Bước giá</span><b>{vnd(s.bid_increment)}</b></div>
                </div>
                <div className={`scard-foot ${isLive(s) ? 'hot' : ''}`}>{keyTime(s)}</div>
              </div>
            </Link>
          ))}
        </div>
        {data && <Pager page={data.page} size={data.size} total={data.total} onPage={setPage} />}
      </div>
    </>
  );
}
