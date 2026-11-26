import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api, ApiError, roomSocketUrl } from '../../api/client';
import type { BidOut, PublicBid, RoomState, Session, SessionStatus } from '../../api/types';
import { useAuth } from '../../auth/AuthContext';
import { Badge, ErrorBox, Loading } from '../../components/ui';
import { countdown, dt, money, parseUtc, SESSION_STATUS, timeOnly, vnd } from '../../format';

// SCR-06 – Phòng đấu giá trực tuyến (FR-15, FR-18 – FR-21, NFR-02)
// Máy trạng thái khối đặt giá: Bảng 4.7.12 (Sẵn sàng / Đang chờ / Đã chấp nhận / Bị từ chối / Mất kết nối / Tạm dừng–Đã đóng)

type Conn = 'connecting' | 'open' | 'lost';
type Pending = { code: string; amount: number; since: number; slow: boolean };
type Feedback = { kind: 'ok' | 'err'; text: string } | null;

const CONFIRM_TIMEOUT_MS = 5000;

function newTransactionCode() {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `tx-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

export default function AuctionRoom() {
  const { id } = useParams();
  const sid = Number(id);
  const { user } = useAuth();
  const isBidder = user?.role === 'BIDDER';

  const [session, setSession] = useState<Session | null>(null);
  const [state, setState] = useState<RoomState | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [conn, setConn] = useState<Conn>('connecting');
  const [offset, setOffset] = useState(0); // giờ máy chủ - giờ máy khách (ms)
  const [now, setNow] = useState(Date.now());
  const [amount, setAmount] = useState(0);
  const [pending, setPending] = useState<Pending | null>(null);
  const [feedback, setFeedback] = useState<Feedback>(null);
  const [pauseReason, setPauseReason] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const amountTouched = useRef(false);

  const applySnapshot = useCallback((s: RoomState) => {
    setState(s);
    const st = parseUtc(s.server_time);
    if (st) setOffset(st.getTime() - Date.now());
    if (!amountTouched.current) setAmount(money(s.minimum_next_bid));
  }, []);

  const loadState = useCallback(async () => {
    try {
      applySnapshot(await api<RoomState>(`/sessions/${sid}/state`));
      setError(null);
    } catch (e) {
      setError(e);
    }
  }, [sid, applySnapshot]);

  // Tải thông tin phiên và trạng thái phòng
  useEffect(() => {
    api<Session>(`/sessions/${sid}`).then(setSession).catch(() => undefined);
    loadState();
  }, [sid, loadState]);

  // Kênh thời gian thực, tự kết nối lại (FR-19, NFR-02)
  useEffect(() => {
    let closed = false;
    let retry = 0;
    let ping: number | undefined;
    let timer: number | undefined;
    const connect = () => {
      setConn('connecting');
      const ws = new WebSocket(roomSocketUrl(sid));
      wsRef.current = ws;
      ws.onopen = () => {
        retry = 0;
        setConn('open');
        ping = window.setInterval(() => ws.readyState === WebSocket.OPEN && ws.send('ping'), 20000);
      };
      ws.onmessage = (ev) => {
        if (ev.data === 'pong') return;
        let msg: { event: string; data: Record<string, unknown> };
        try {
          msg = JSON.parse(ev.data);
        } catch {
          return;
        }
        if (msg.event === 'session.snapshot') {
          applySnapshot(msg.data as unknown as RoomState);
        } else if (msg.event === 'bid.accepted') {
          const d = msg.data as unknown as PublicBid & { highest_accepted: string; minimum_next_bid: string };
          setState((s) => {
            if (!s || s.recent_bids.some((b) => b.sequence_no === d.sequence_no)) return s;
            const bid: PublicBid = { sequence_no: d.sequence_no, bidder_alias: d.bidder_alias, amount: d.amount, result: 'ACCEPTED', server_time: d.server_time };
            return { ...s, highest_accepted: d.highest_accepted, minimum_next_bid: d.minimum_next_bid, recent_bids: [bid, ...s.recent_bids].slice(0, 50) };
          });
          setAmount((a) => (amountTouched.current && a > money(d.highest_accepted) ? a : money(d.minimum_next_bid)));
        } else if (msg.event === 'session.status_changed') {
          const d = msg.data as { status: SessionStatus; end_time?: string; reason?: string | null };
          setState((s) => (s ? { ...s, status: d.status, end_time: d.end_time ?? s.end_time } : s));
          setPauseReason(d.status === 'PAUSED' ? d.reason ?? 'Đấu giá viên tạm dừng phiên' : null);
        }
      };
      ws.onclose = (ev) => {
        window.clearInterval(ping);
        if (closed) return;
        if (ev.code === 1008) {
          // Máy chủ từ chối vào phòng (không đủ điều kiện / token hết hạn)
          setError(new ApiError(403, 'ROOM_DENIED', ev.reason || 'Bạn không được vào phòng đấu giá này'));
          setConn('lost');
          return;
        }
        setConn('lost');
        retry += 1;
        timer = window.setTimeout(connect, Math.min(10000, 1000 * 2 ** Math.min(retry, 4)));
      };
    };
    connect();
    return () => {
      closed = true;
      window.clearInterval(ping);
      window.clearTimeout(timer);
      wsRef.current?.close();
    };
  }, [sid, applySnapshot]);

  // Đồng hồ: tính theo giờ máy chủ (UI-02)
  useEffect(() => {
    const t = window.setInterval(() => {
      setNow(Date.now());
      setPending((p) => (p && !p.slow && Date.now() - p.since > CONFIRM_TIMEOUT_MS ? { ...p, slow: true } : p));
    }, 250);
    return () => window.clearInterval(t);
  }, []);

  const send = async (code: string, value: number) => {
    setPending({ code, amount: value, since: Date.now(), slow: false });
    setFeedback(null);
    try {
      const res = await api<BidOut>(`/sessions/${sid}/bids`, { method: 'POST', body: { amount: value, transaction_code: code } });
      if (res.result === 'ACCEPTED') {
        setFeedback({ kind: 'ok', text: `Lệnh ${vnd(res.amount)} đã được chấp nhận (lượt #${res.sequence_no}).` });
        amountTouched.current = false;
      } else {
        setFeedback({ kind: 'err', text: `Lệnh ${vnd(res.amount)} lúc ${timeOnly(res.server_time)} bị từ chối: ${res.rejection_reason ?? ''}` });
      }
      setPending(null);
      if (conn !== 'open') loadState();
    } catch (e) {
      if (e instanceof ApiError && e.status !== 0) {
        setFeedback({ kind: 'err', text: e.message });
        setPending(null);
      } else {
        // Không rõ máy chủ đã nhận hay chưa: giữ mã giao dịch để hỏi lại, không tạo lệnh mới
        setPending((p) => (p ? { ...p, slow: true } : p));
      }
    }
  };

  if (!state && !error) return <Loading />;
  if (!state)
    return (
      <div className="wrap">
        <ErrorBox error={error} />
        <div style={{ marginTop: 10 }}><Link to="/my/registrations">‹ Về hồ sơ của tôi</Link></div>
      </div>
    );

  const st = SESSION_STATUS[state.status];
  const end = parseUtc(state.end_time)?.getTime() ?? 0;
  const remaining = end - (now + offset);
  const accepting = state.status === 'IN_PROGRESS' && remaining > 0;
  const step = money(state.bid_increment);
  const minBid = money(state.minimum_next_bid);
  const validStep = (amount - money(state.starting_price)) % step === 0;
  const canSend = isBidder && accepting && conn === 'open' && !pending && amount >= minBid && validStep;
  const highest = state.highest_accepted;
  const top = state.recent_bids.find((b) => b.result === 'ACCEPTED');

  let blocked: string | null = null;
  if (conn !== 'open') blocked = 'Đang kết nối lại… Nút Gửi giá tạm khóa.';
  else if (state.status === 'PAUSED') blocked = `Phiên tạm dừng${pauseReason ? `: ${pauseReason}` : ''}.`;
  else if (state.status === 'UPCOMING') blocked = `Phiên chưa mở. Dự kiến bắt đầu ${dt(state.start_time)}.`;
  else if (state.status === 'CANCELLED') blocked = 'Phiên đã bị hủy.';
  else if (state.status === 'ENDED') blocked = 'Phiên đã kết thúc. Kết quả chính thức do Đấu giá viên xác nhận.';
  else if (remaining <= 0) blocked = 'Đã đóng nhận giá – kết quả chờ Đấu giá viên xác nhận.';

  return (
    <>
      <div className="top">
        <Link to="/" className="logo" style={{ textDecoration: 'none' }}>DGTT<small>Phòng đấu giá</small></Link>
        <div className="hide-sm"><b>{state.code}</b>{session?.asset_name && <> · {session.asset_name}</>}</div>
        <div className="sp" />
        <Badge color={conn === 'open' ? 'green' : 'red'}>{conn === 'open' ? '● Đã kết nối' : '● Mất kết nối'}</Badge>
        {state.my_alias && <span className="mut">Mã của bạn: <b>{state.my_alias}</b></span>}
        <Link className="btn" to={isBidder ? '/my/registrations' : `/manage/sessions/${sid}`}>Rời phòng</Link>
      </div>
      {conn === 'lost' && <div className="warn" style={{ borderRadius: 0 }}>Mất kết nối tới máy chủ, đang thử kết nối lại. Khi có lại kết nối, dữ liệu sẽ được đồng bộ từ máy chủ.</div>}
      <div className="wrap">
        <ErrorBox error={error} />
        <div className="row">
          <div className="col" style={{ flex: 1.5 }}>
            <div className="card" style={{ display: 'flex', gap: 20, alignItems: 'center', flexWrap: 'wrap' }}>
              <div style={{ flex: 1 }}>
                <Badge color={st.color}>{st.label}</Badge>
                <div className="mut" style={{ marginTop: 8 }}>Giá cao nhất đã được chấp nhận</div>
                <div className="big-price">{highest ? vnd(highest) : 'Chưa có lượt giá'}</div>
                {top && <div className="mut">Người giữ giá: {top.bidder_alias} · lượt #{top.sequence_no} lúc {timeOnly(top.server_time)}</div>}
              </div>
              <div className="clock">
                <div style={{ fontSize: 12, opacity: 0.7 }}>{state.status === 'UPCOMING' ? 'Bắt đầu lúc' : 'Thời gian còn lại'}</div>
                <b>{state.status === 'UPCOMING' ? timeOnly(state.start_time) : state.status === 'PAUSED' ? 'Tạm dừng' : state.status === 'ENDED' || state.status === 'CANCELLED' ? 'Đã đóng' : countdown(remaining)}</b>
                <div style={{ fontSize: 11, opacity: 0.7 }}>Kết thúc {timeOnly(state.end_time)} (giờ máy chủ)</div>
              </div>
            </div>

            {isBidder ? (
              <div className="card">
                <div className="h2">Đặt giá</div>
                <div className="row" style={{ gap: 20, marginBottom: 10, flexDirection: 'row', flexWrap: 'wrap' }}>
                  <div><span className="mut">Giá khởi điểm</span><br /><b>{vnd(state.starting_price)}</b></div>
                  <div><span className="mut">Bước giá</span><br /><b>{vnd(state.bid_increment)}</b></div>
                  <div><span className="mut">Giá hợp lệ tối thiểu</span><br /><b style={{ color: '#1d4ed8' }}>{vnd(minBid)}</b></div>
                </div>
                <div className="bid-row">
                  <button className="btn" disabled={amount - step < minBid} onClick={() => { amountTouched.current = true; setAmount(amount - step); }}>−</button>
                  <input
                    className="in"
                    style={{ flex: 1, minWidth: 150, fontSize: 20, fontWeight: 600, textAlign: 'right' }}
                    value={amount.toLocaleString('vi-VN')}
                    onChange={(e) => { amountTouched.current = true; setAmount(Number(e.target.value.replace(/\D/g, '')) || 0); }}
                    inputMode="numeric"
                  />
                  <button className="btn" onClick={() => { amountTouched.current = true; setAmount(amount + step); }}>+</button>
                  <button className="btn p lg send-btn" disabled={!canSend} onClick={() => send(newTransactionCode(), amount)}>Gửi giá</button>
                </div>
                <div className="row" style={{ gap: 8, marginTop: 10, flexDirection: 'row', flexWrap: 'wrap' }}>
                  <span className="mut" style={{ alignSelf: 'center' }}>Chọn nhanh:</span>
                  {[1, 2, 5].map((k) => (
                    <button key={k} className="btn" onClick={() => { amountTouched.current = true; setAmount(minBid + (k - 1) * step); }}>+{k} bước</button>
                  ))}
                </div>
                {!validStep && amount > 0 && <div className="errt">Mức giá phải bằng giá khởi điểm cộng bội số của bước giá.</div>}
                {amount < minBid && amount > 0 && <div className="errt">Mức giá thấp hơn giá hợp lệ tối thiểu.</div>}
                <div style={{ marginTop: 12 }} className="col">
                  {blocked && <div className="note">{blocked}</div>}
                  {state.status === 'ENDED' && <Link className="btn" to={`/sessions/${state.session_id}`}>Xem kết quả chính thức và biên bản</Link>}
                  {pending && !pending.slow && <div className="note">⏳ Lệnh <b>{vnd(pending.amount)}</b> đang chờ máy chủ xác nhận… <span className="mut">(chưa phải giá đã nhận)</span></div>}
                  {pending?.slow && (
                    <div className="warn">
                      Chưa nhận được xác nhận cho lệnh {vnd(pending.amount)}. Hệ thống không tự gửi lại.
                      <div className="row" style={{ gap: 8, marginTop: 6, flexDirection: 'row' }}>
                        {/* Gửi lại CÙNG mã giao dịch: máy chủ trả kết quả cũ nếu đã nhận, không tạo lệnh trùng */}
                        <button className="btn" onClick={() => send(pending.code, pending.amount)}>Hỏi lại kết quả</button>
                        <button className="btn" onClick={() => { setPending(null); loadState(); }}>Bỏ qua và đồng bộ</button>
                      </div>
                    </div>
                  )}
                  {feedback && <div className={feedback.kind === 'ok' ? 'ok-box' : 'err-box'}>{feedback.kind === 'ok' ? '✓ ' : '✕ '}{feedback.text}</div>}
                </div>
              </div>
            ) : (
              <div className="card note">Bạn đang xem phòng với vai trò nội bộ, không thể trả giá.</div>
            )}
          </div>
          <div className="col" style={{ flex: 1 }}>
            <div className="card" style={{ flex: 1 }}>
              <div className="h2">Diễn biến trả giá</div>
              <table>
                <thead><tr><th>Lượt</th><th>Người trả</th><th>Mức giá</th><th>Giờ máy chủ</th></tr></thead>
                <tbody>
                  {state.recent_bids.filter((b) => b.result === 'ACCEPTED').map((b, i) => (
                    <tr key={b.sequence_no} style={i === 0 ? { background: '#f0fdf4', fontWeight: 600 } : undefined}>
                      <td>#{b.sequence_no}</td>
                      <td>{b.bidder_alias}{b.bidder_alias && b.bidder_alias === state.my_alias && ' (bạn)'}</td>
                      <td>{vnd(b.amount)}</td>
                      <td>{timeOnly(b.server_time)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {state.recent_bids.length === 0 && <div className="mut" style={{ padding: 10 }}>Chưa có lượt giá nào.</div>}
              <div className="mut" style={{ marginTop: 8 }}>Hiển thị bằng mã ẩn danh. Chỉ lượt giá đã được máy chủ chấp nhận.</div>
            </div>
            <div className="card">
              <div className="h2">Thông tin phiên</div>
              <div style={{ lineHeight: 1.8, fontSize: 13 }}>
                Bắt đầu: {dt(state.start_time)}<br />
                Kết thúc: {dt(state.end_time)}<br />
                Lượt đầu được trả bằng giá khởi điểm
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
