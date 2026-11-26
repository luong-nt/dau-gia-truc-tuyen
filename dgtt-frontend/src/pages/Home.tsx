import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';
import type { AssetDetail, Page, Session, SessionStatus } from '../api/types';
import { AssetImage, firstImage } from '../components/AssetImage';
import { Badge, ErrorBox, Loading, Pager, useLoad } from '../components/ui';
import { dt, SESSION_STATUS, vnd } from '../format';

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
function CardImage({ assetId }: { assetId: number }) {
  const { data } = useLoad(() => api<AssetDetail>(`/assets/${assetId}`).catch(() => null), [assetId]);
  return <AssetImage assetId={assetId} att={firstImage(data?.attachments)} height={110} />;
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

  return (
    <>
      <div style={{ background: '#1e3a8a', color: '#fff', padding: '26px 28px' }}>
        <div style={{ fontSize: 22, fontWeight: 600 }}>Tìm kiếm tài sản đấu giá</div>
        <div style={{ opacity: 0.8, margin: '4px 0 14px' }}>
          Thông tin công khai theo thông báo đấu giá. Giờ hiển thị theo GMT+7.
        </div>
        <form
          className="row"
          style={{ gap: 10 }}
          onSubmit={(e) => {
            e.preventDefault();
            setPage(1);
            setQuery(keyword.trim());
          }}
        >
          <input
            className="in"
            style={{ flex: 3 }}
            placeholder="Nhập tên tài sản hoặc mã phiên…"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
          />
          <button className="btn p" style={{ background: '#f59e0b', borderColor: '#f59e0b' }}>Tìm kiếm</button>
        </form>
      </div>
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
            <Link key={s.session_id} to={`/sessions/${s.session_id}`} className="card" style={{ padding: 0, overflow: 'hidden', color: 'inherit', textDecoration: 'none' }}>
              <CardImage assetId={s.asset_id} />
              <div style={{ padding: '12px 14px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                  <span className="mut">{s.asset_code} · {s.code}</span>
                  <Badge color={SESSION_STATUS[s.status].color}>{SESSION_STATUS[s.status].label}</Badge>
                </div>
                <div style={{ fontWeight: 600, margin: '6px 0 8px', minHeight: 38 }}>{s.asset_name}</div>
                <div className="mut">Giá khởi điểm</div>
                <div style={{ fontSize: 17, fontWeight: 700, color: '#1d4ed8' }}>{vnd(s.starting_price)}</div>
                <div className="mut" style={{ marginTop: 6 }}>{keyTime(s)}</div>
              </div>
            </Link>
          ))}
        </div>
        {data && <Pager page={data.page} size={data.size} total={data.total} onPage={setPage} />}
      </div>
    </>
  );
}
