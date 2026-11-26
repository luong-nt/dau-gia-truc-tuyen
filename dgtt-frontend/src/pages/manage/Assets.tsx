import { useState, type ChangeEvent } from 'react';
import { Link } from 'react-router-dom';
import { api, downloadFile } from '../../api/client';
import type { Asset, AssetDetail, AssetOwner, AssetStatus, Page } from '../../api/types';
import { AssetImage } from '../../components/AssetImage';
import { Badge, ErrorBox, Loading, Pager, ReasonDialog, useLoad } from '../../components/ui';
import { ASSET_STATUS, dt, fileSize, OWNER_TYPE, SESSION_STATUS, vnd } from '../../format';

// SCR-07 – Quản lý tài sản và người có tài sản (FR-05, FR-06, FR-07)
// API: /assets, /asset-owners, /assets/{id}/attachments (backend TASK-007, TASK-008, TASK-014)
const FILTERS: (AssetStatus | '')[] = ['', 'UPCOMING', 'IN_AUCTION', 'ENDED', 'SUSPENDED_CANCELLED'];
const MAX_MB = 10;

export default function Assets() {
  const [tab, setTab] = useState<'assets' | 'owners'>('assets');
  return (
    <div className="col">
      <div className="h1">Quản lý tài sản</div>
      <div className="tabs" style={{ marginBottom: 0 }}>
        <button className={`btn ${tab === 'assets' ? 'p' : ''}`} onClick={() => setTab('assets')}>Tài sản</button>
        <button className={`btn ${tab === 'owners' ? 'p' : ''}`} onClick={() => setTab('owners')}>Người có tài sản</button>
      </div>
      {tab === 'assets' ? <AssetTab /> : <OwnerTab />}
    </div>
  );
}

// ---------------------------------------------------------------- Tài sản
function AssetTab() {
  const [status, setStatus] = useState<AssetStatus | ''>('');
  const [keyword, setKeyword] = useState('');
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<number | null>(null);
  const [creating, setCreating] = useState(false);
  const list = useLoad(
    () => api<Page<Asset>>('/assets', { query: { status, keyword: query, page, size: 15 } }),
    [status, query, page],
  );

  return (
    <div className="row" style={{ alignItems: 'flex-start' }}>
      <div className="col" style={{ flex: 1.3, minWidth: 0 }}>
        <div className="card col">
          <form
            className="row"
            style={{ gap: 8 }}
            onSubmit={(e) => {
              e.preventDefault();
              setPage(1);
              setQuery(keyword.trim());
            }}
          >
            <input className="in" placeholder="Tìm theo mã hoặc tên tài sản…" value={keyword} onChange={(e) => setKeyword(e.target.value)} />
            <button className="btn">Tìm</button>
            <button type="button" className="btn p" style={{ whiteSpace: 'nowrap' }} onClick={() => { setCreating(true); setSelected(null); }}>
              + Thêm tài sản
            </button>
          </form>
          <div className="tabs" style={{ marginBottom: 0 }}>
            {FILTERS.map((f) => (
              <button key={f || 'all'} className={`btn ${status === f ? 'p' : ''}`} onClick={() => { setStatus(f); setPage(1); }}>
                {f ? ASSET_STATUS[f].label : 'Tất cả'}
              </button>
            ))}
          </div>
          <ErrorBox error={list.error} />
          {list.loading && <Loading />}
          {list.data && (
            <table>
              <thead><tr><th>Mã</th><th>Tên tài sản</th><th>Trạng thái</th><th>Công khai</th><th>Tạo lúc</th></tr></thead>
              <tbody>
                {list.data.items.length === 0 && <tr><td colSpan={5} className="mut">Không có tài sản phù hợp.</td></tr>}
                {list.data.items.map((a) => (
                  <tr
                    key={a.asset_id}
                    onClick={() => { setSelected(a.asset_id); setCreating(false); }}
                    style={{ cursor: 'pointer', background: selected === a.asset_id ? '#eff6ff' : undefined }}
                  >
                    <td>{a.asset_code}</td>
                    <td>{a.name}</td>
                    <td><Badge color={ASSET_STATUS[a.status].color}>{ASSET_STATUS[a.status].label}</Badge></td>
                    <td>{a.is_public ? 'Có' : <span className="mut">Chưa</span>}</td>
                    <td className="mut">{dt(a.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {list.data && <Pager page={list.data.page} size={list.data.size} total={list.data.total} onPage={setPage} />}
        </div>
      </div>
      <div className="col" style={{ flex: 1, minWidth: 0 }}>
        {creating && (
          <AssetForm
            onCancel={() => setCreating(false)}
            onSaved={async (a) => { setCreating(false); await list.reload(); setSelected(a.asset_id); }}
          />
        )}
        {!creating && selected && (
          <AssetPanel key={selected} assetId={selected} onChanged={list.reload} onDeleted={async () => { setSelected(null); await list.reload(); }} />
        )}
        {!creating && !selected && (
          <div className="card mut">Chọn một tài sản trong danh sách để xem chi tiết, sửa, tải ảnh và tài liệu.</div>
        )}
      </div>
    </div>
  );
}

function AssetForm({ existing, onSaved, onCancel }: { existing?: AssetDetail; onSaved: (a: AssetDetail) => void; onCancel: () => void }) {
  const owners = useLoad(() => api<Page<AssetOwner>>('/asset-owners', { query: { size: 100 } }), []);
  const [f, setF] = useState({
    asset_code: existing?.asset_code ?? '',
    owner_id: existing?.owner?.owner_id ? String(existing.owner.owner_id) : '',
    name: existing?.name ?? '',
    description: existing?.description ?? '',
    is_public: existing?.is_public ?? false,
    reason: '',
  });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const set = (k: keyof typeof f) => (e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
    setF({ ...f, [k]: e.target.type === 'checkbox' ? (e.target as HTMLInputElement).checked : e.target.value });
  // UI-08 / FR-05: tài sản đã công khai thì mọi thay đổi phải có lý do
  const needReason = !!existing?.is_public;

  return (
    <form
      className="card form"
      onSubmit={async (e) => {
        e.preventDefault();
        if (needReason && !f.reason.trim()) {
          setErr(new Error('Tài sản đang công khai: vui lòng nhập lý do thay đổi.'));
          return;
        }
        setBusy(true);
        setErr(null);
        try {
          const body = { owner_id: Number(f.owner_id), name: f.name, description: f.description || null, is_public: f.is_public };
          const saved = existing
            ? await api<AssetDetail>(`/assets/${existing.asset_id}`, { method: 'PUT', body: { ...body, reason: f.reason.trim() || null } })
            : await api<AssetDetail>('/assets', { method: 'POST', body: { ...body, asset_code: f.asset_code } });
          onSaved(saved);
        } catch (e2) {
          setErr(e2);
        } finally {
          setBusy(false);
        }
      }}
    >
      <div className="h2">{existing ? `Sửa tài sản ${existing.asset_code}` : 'Thêm tài sản'}</div>
      <label>Mã tài sản *<input className="in" required maxLength={30} disabled={!!existing} value={f.asset_code} onChange={set('asset_code')} placeholder="VD: TS-0002" /></label>
      <label>
        Người có tài sản *
        <select className="in" required value={f.owner_id} onChange={set('owner_id')}>
          <option value="">— Chọn —</option>
          {owners.data?.items.map((o) => (
            <option key={o.owner_id} value={o.owner_id}>{o.name} ({OWNER_TYPE[o.owner_type]}, {o.id_number})</option>
          ))}
        </select>
        {owners.data && owners.data.items.length === 0 && <span className="mut">Chưa có người có tài sản: thêm ở thẻ "Người có tài sản" trước.</span>}
      </label>
      <label>Tên tài sản *<input className="in" required maxLength={200} value={f.name} onChange={set('name')} /></label>
      <label>Mô tả<textarea className="in" rows={4} maxLength={5000} value={f.description} onChange={set('description')} /></label>
      <label style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
        <input type="checkbox" checked={f.is_public} onChange={set('is_public')} /> Công khai trên trang tra cứu
      </label>
      {existing && (
        <label>
          Lý do thay đổi{needReason ? ' *' : ' (không bắt buộc)'}
          <textarea className="in" rows={2} value={f.reason} onChange={set('reason')} />
          {needReason && <span className="mut">Tài sản đang công khai: mọi thay đổi được ghi nhật ký kèm lý do.</span>}
        </label>
      )}
      <ErrorBox error={err ?? owners.error} />
      <div className="row" style={{ justifyContent: 'flex-end', gap: 8 }}>
        <button type="button" className="btn" onClick={onCancel}>Hủy</button>
        <button className="btn p" disabled={busy}>{busy ? 'Đang lưu…' : 'Lưu'}</button>
      </div>
    </form>
  );
}

function AssetPanel({ assetId, onChanged, onDeleted }: { assetId: number; onChanged: () => void; onDeleted: () => void }) {
  const { data: a, error, loading, reload } = useLoad(() => api<AssetDetail>(`/assets/${assetId}`), [assetId]);
  const [editing, setEditing] = useState(false);
  const [dialog, setDialog] = useState<'suspend' | 'delete' | null>(null);
  const [fileType, setFileType] = useState<'ASSET_IMAGE' | 'ASSET_DOCUMENT'>('ASSET_IMAGE');
  const [upErr, setUpErr] = useState<unknown>(null);
  const [uploading, setUploading] = useState(false);

  if (loading && !a) return <Loading />;
  if (error || !a) return <ErrorBox error={error ?? 'Không tìm thấy tài sản'} />;
  if (editing)
    return <AssetForm existing={a} onCancel={() => setEditing(false)} onSaved={async () => { setEditing(false); await reload(); onChanged(); }} />;

  const asset = a;
  const images = asset.attachments.filter((x) => x.file_type === 'ASSET_IMAGE');
  const docs = asset.attachments.filter((x) => x.file_type === 'ASSET_DOCUMENT');
  const activeSession = asset.sessions.some((s) => !['ENDED', 'CANCELLED'].includes(s.status));
  const canSuspend = asset.status === 'UPCOMING' && !activeSession;
  const canDelete = asset.sessions.length === 0;
  const allowed = fileType === 'ASSET_IMAGE' ? ['jpg', 'jpeg', 'png'] : ['pdf', 'jpg', 'jpeg', 'png'];

  async function upload(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    // Kiểm tra ngay tại giao diện (UI-04); máy chủ vẫn kiểm tra lại
    const ext = file.name.split('.').pop()?.toLowerCase() ?? '';
    if (!allowed.includes(ext)) return setUpErr(new Error(`Định dạng không được hỗ trợ. Chỉ chấp nhận: ${allowed.join(', ')}`));
    if (file.size > MAX_MB * 1024 * 1024) return setUpErr(new Error(`Tệp vượt quá dung lượng cho phép (${MAX_MB} MB)`));
    const fd = new FormData();
    fd.append('file', file);
    fd.append('file_type', fileType);
    setUploading(true);
    setUpErr(null);
    try {
      await api(`/assets/${asset.asset_id}/attachments`, { method: 'POST', form: fd });
      await reload();
    } catch (e2) {
      setUpErr(e2);
    } finally {
      setUploading(false);
    }
  }

  async function removeAttachment(id: number) {
    setUpErr(null);
    try {
      await api(`/assets/${asset.asset_id}/attachments/${id}`, { method: 'DELETE' });
      await reload();
    } catch (e2) {
      setUpErr(e2);
    }
  }

  return (
    <div className="col">
      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
          <div>
            <div className="mut">{asset.asset_code}</div>
            <div className="h2" style={{ margin: '2px 0 6px' }}>{asset.name}</div>
          </div>
          <div><Badge color={ASSET_STATUS[asset.status].color}>{ASSET_STATUS[asset.status].label}</Badge></div>
        </div>
        <table className="kv"><tbody>
          <tr><td>Công khai</td><td>{asset.is_public ? 'Có' : 'Chưa công khai'}</td></tr>
          <tr><td>Người có tài sản</td><td>{asset.owner ? `${asset.owner.name} (${OWNER_TYPE[asset.owner.owner_type]})` : '—'}</td></tr>
          <tr><td>Tạo lúc</td><td>{dt(asset.created_at)}</td></tr>
        </tbody></table>
        {asset.description && <div style={{ whiteSpace: 'pre-wrap', fontSize: 13, marginTop: 10 }}>{asset.description}</div>}
        <div className="row" style={{ gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
          <button className="btn" onClick={() => setEditing(true)} disabled={asset.status === 'SUSPENDED_CANCELLED'}>Sửa</button>
          <button
            className="btn o"
            disabled={!canSuspend}
            title={canSuspend ? undefined : 'Chỉ ngừng được tài sản Sắp đấu giá và không có phiên chưa kết thúc'}
            onClick={() => setDialog('suspend')}
          >
            Ngừng tài sản…
          </button>
          <button
            className="btn r"
            disabled={!canDelete}
            title={canDelete ? undefined : 'Tài sản đã có phiên đấu giá, chỉ được ngừng sử dụng'}
            onClick={() => setDialog('delete')}
          >
            Xóa
          </button>
        </div>
        {!canDelete && <div className="mut" style={{ marginTop: 6 }}>Tài sản đã gắn phiên đấu giá nên không xóa được, chỉ ngừng sử dụng.</div>}
      </div>

      <div className="card col">
        <div className="h2" style={{ margin: 0 }}>Ảnh và tài liệu</div>
        {images.length > 0 && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8 }}>
            {images.map((im) => (
              <div key={im.attachment_id} style={{ border: '1px solid #e5e7eb', borderRadius: 6, overflow: 'hidden' }}>
                <AssetImage assetId={asset.asset_id} att={im} height={90} />
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 4, padding: '4px 6px', fontSize: 11 }}>
                  <span className="mut" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{im.file_name}</span>
                  <a href="#" style={{ color: '#b91c1c' }} onClick={(e) => { e.preventDefault(); removeAttachment(im.attachment_id); }}>Xóa</a>
                </div>
              </div>
            ))}
          </div>
        )}
        {docs.map((d) => (
          <div key={d.attachment_id} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
            <a href="#" onClick={(e) => { e.preventDefault(); downloadFile(`/assets/${asset.asset_id}/attachments/${d.attachment_id}`, undefined, d.file_name); }}>
              {d.file_name}
            </a>
            <span className="mut">{fileSize(d.file_size)} · <a href="#" style={{ color: '#b91c1c' }} onClick={(e) => { e.preventDefault(); removeAttachment(d.attachment_id); }}>Xóa</a></span>
          </div>
        ))}
        {asset.attachments.length === 0 && <div className="mut">Chưa có ảnh hoặc tài liệu.</div>}
        <div className="row" style={{ gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <select className="in" style={{ width: 'auto' }} value={fileType} onChange={(e) => setFileType(e.target.value as typeof fileType)}>
            <option value="ASSET_IMAGE">Ảnh (JPG, PNG)</option>
            <option value="ASSET_DOCUMENT">Tài liệu (PDF, JPG, PNG)</option>
          </select>
          <label className="btn" style={{ cursor: 'pointer' }}>
            {uploading ? 'Đang tải lên…' : 'Chọn tệp tải lên'}
            <input type="file" accept={allowed.map((x) => '.' + x).join(',')} style={{ display: 'none' }} disabled={uploading} onChange={upload} />
          </label>
          <span className="mut">Tối đa {MAX_MB} MB/tệp</span>
        </div>
        <ErrorBox error={upErr} />
      </div>

      <div className="card">
        <div className="h2">Phiên đấu giá của tài sản</div>
        {asset.sessions.length === 0 ? (
          <div className="mut">Chưa có phiên. Tạo phiên tại mục Phiên đấu giá.</div>
        ) : (
          <table><tbody>
            {asset.sessions.map((s) => (
              <tr key={s.session_id}>
                <td><Link to={`/manage/sessions/${s.session_id}`}>{s.code}</Link></td>
                <td><Badge color={SESSION_STATUS[s.status].color}>{SESSION_STATUS[s.status].label}</Badge></td>
                <td>{vnd(s.starting_price)}</td>
                <td className="mut">{dt(s.start_time)}</td>
              </tr>
            ))}
          </tbody></table>
        )}
      </div>

      {dialog === 'suspend' && (
        <ReasonDialog
          title="Ngừng tài sản"
          message={`Chuyển ${asset.asset_code} sang trạng thái "Tạm dừng / Hủy". Tài sản sẽ không dùng được để tạo phiên mới.`}
          requireReason
          confirmText="Ngừng tài sản"
          danger
          onConfirm={async (reason) => {
            await api(`/assets/${asset.asset_id}/status`, { method: 'PATCH', body: { status: 'SUSPENDED_CANCELLED', reason } });
            await reload();
            onChanged();
          }}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog === 'delete' && (
        <ReasonDialog
          title="Xóa tài sản"
          message={`Xóa vĩnh viễn ${asset.asset_code} – ${asset.name} cùng ảnh, tài liệu. Không thể hoàn tác.`}
          reasonLabel="Ghi chú"
          confirmText="Xóa tài sản"
          danger
          onConfirm={async () => {
            await api(`/assets/${asset.asset_id}`, { method: 'DELETE' });
            onDeleted();
          }}
          onClose={() => setDialog(null)}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------- Người có tài sản
function OwnerTab() {
  const [keyword, setKeyword] = useState('');
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [edit, setEdit] = useState<AssetOwner | 'new' | null>(null);
  const list = useLoad(() => api<Page<AssetOwner>>('/asset-owners', { query: { keyword: query, page, size: 15 } }), [query, page]);
  return (
    <div className="row" style={{ alignItems: 'flex-start' }}>
      <div className="card col" style={{ flex: 1.3, minWidth: 0 }}>
        <form className="row" style={{ gap: 8 }} onSubmit={(e) => { e.preventDefault(); setPage(1); setQuery(keyword.trim()); }}>
          <input className="in" placeholder="Tìm theo tên hoặc số giấy tờ…" value={keyword} onChange={(e) => setKeyword(e.target.value)} />
          <button className="btn">Tìm</button>
          <button type="button" className="btn p" style={{ whiteSpace: 'nowrap' }} onClick={() => setEdit('new')}>+ Thêm</button>
        </form>
        <ErrorBox error={list.error} />
        {list.loading && <Loading />}
        {list.data && (
          <table>
            <thead><tr><th>Tên</th><th>Loại</th><th>Số giấy tờ</th><th>Liên hệ</th></tr></thead>
            <tbody>
              {list.data.items.length === 0 && <tr><td colSpan={4} className="mut">Chưa có dữ liệu.</td></tr>}
              {list.data.items.map((o) => (
                <tr key={o.owner_id} style={{ cursor: 'pointer' }} onClick={() => setEdit(o)}>
                  <td>{o.name}{o.representative_name && <div className="mut">Đại diện: {o.representative_name}</div>}</td>
                  <td>{OWNER_TYPE[o.owner_type]}</td>
                  <td>{o.id_number}</td>
                  <td className="mut">{[o.phone, o.email].filter(Boolean).join(' · ') || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {list.data && <Pager page={list.data.page} size={list.data.size} total={list.data.total} onPage={setPage} />}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        {edit ? (
          <OwnerForm
            key={edit === 'new' ? 'new' : edit.owner_id}
            existing={edit === 'new' ? undefined : edit}
            onCancel={() => setEdit(null)}
            onSaved={async () => { setEdit(null); await list.reload(); }}
          />
        ) : (
          <div className="card mut">Người có tài sản là cá nhân hoặc tổ chức ủy quyền bán đấu giá. Chọn một dòng để sửa.</div>
        )}
      </div>
    </div>
  );
}

function OwnerForm({ existing, onSaved, onCancel }: { existing?: AssetOwner; onSaved: () => void; onCancel: () => void }) {
  const [f, setF] = useState({
    owner_type: existing?.owner_type ?? 'INDIVIDUAL',
    name: existing?.name ?? '',
    id_number: existing?.id_number ?? '',
    representative_name: existing?.representative_name ?? '',
    phone: existing?.phone ?? '',
    email: existing?.email ?? '',
    address: existing?.address ?? '',
  });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const set = (k: keyof typeof f) => (e: ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.value });
  const org = f.owner_type === 'ORGANIZATION';
  return (
    <form
      className="card form"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setErr(null);
        const body = Object.fromEntries(Object.entries(f).map(([k, v]) => [k, v.trim() === '' ? null : v.trim()]));
        try {
          if (existing) await api(`/asset-owners/${existing.owner_id}`, { method: 'PUT', body });
          else await api('/asset-owners', { method: 'POST', body });
          onSaved();
        } catch (e2) {
          setErr(e2);
        } finally {
          setBusy(false);
        }
      }}
    >
      <div className="h2">{existing ? 'Sửa người có tài sản' : 'Thêm người có tài sản'}</div>
      <label>
        Loại *
        <select className="in" value={f.owner_type} onChange={set('owner_type')}>
          <option value="INDIVIDUAL">Cá nhân</option>
          <option value="ORGANIZATION">Tổ chức</option>
        </select>
      </label>
      <label>{org ? 'Tên tổ chức *' : 'Họ và tên *'}<input className="in" required maxLength={200} value={f.name} onChange={set('name')} /></label>
      <label>{org ? 'Mã số doanh nghiệp / thuế *' : 'Số CCCD / hộ chiếu *'}<input className="in" required maxLength={20} value={f.id_number} onChange={set('id_number')} /></label>
      {org && <label>Người đại diện<input className="in" maxLength={100} value={f.representative_name} onChange={set('representative_name')} /></label>}
      <div className="row" style={{ gap: 8 }}>
        <label style={{ flex: 1 }}>Điện thoại<input className="in" pattern="[0-9+]{9,15}" title="9–15 chữ số, có thể có dấu +" value={f.phone} onChange={set('phone')} /></label>
        <label style={{ flex: 1 }}>Email<input className="in" type="email" value={f.email} onChange={set('email')} /></label>
      </div>
      <label>Địa chỉ<input className="in" maxLength={255} value={f.address} onChange={set('address')} /></label>
      <ErrorBox error={err} />
      <div className="row" style={{ justifyContent: 'flex-end', gap: 8 }}>
        <button type="button" className="btn" onClick={onCancel}>Hủy</button>
        <button className="btn p" disabled={busy}>{busy ? 'Đang lưu…' : 'Lưu'}</button>
      </div>
    </form>
  );
}
