import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { AssetAttachment } from '../api/types';

/**
 * Ảnh tài sản tải qua API có kiểm tra quyền (backend không trả đường dẫn lưu trữ nội bộ).
 * Gửi kèm token nếu có, nên Nhân viên xem được cả ảnh của tài sản chưa công khai.
 */
export function AssetImage({ assetId, att, height = 110, alt }: { assetId: number; att?: AssetAttachment | null; height?: number; alt?: string }) {
  const [src, setSrc] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (!att) return;
    let url: string | null = null;
    let cancelled = false;
    api<Response>(`/assets/${assetId}/attachments/${att.attachment_id}`, { raw: true })
      .then((r) => r.blob())
      .then((b) => {
        if (cancelled) return;
        url = URL.createObjectURL(b);
        setSrc(url);
      })
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [assetId, att?.attachment_id]);
  if (!att || failed || !src)
    return <div className="img" style={{ height, borderRadius: 0 }}>{att && !failed ? 'Đang tải ảnh…' : 'Chưa có ảnh'}</div>;
  return <img src={src} alt={alt ?? att.file_name} style={{ width: '100%', height, objectFit: 'cover', display: 'block' }} />;
}

/** Ảnh đầu tiên theo thứ tự hiển thị. */
export function firstImage(atts: AssetAttachment[] | undefined | null): AssetAttachment | null {
  const imgs = (atts ?? []).filter((a) => a.file_type === 'ASSET_IMAGE');
  imgs.sort((a, b) => (a.display_order ?? 0) - (b.display_order ?? 0) || a.attachment_id - b.attachment_id);
  return imgs[0] ?? null;
}
