import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';
import { api, getToken, setToken, setUnauthorizedHandler } from '../api/client';
import type { Role, TokenResponse, User } from '../api/types';

type AuthState = {
  user: User | null;
  ready: boolean;
  login: (login: string, password: string) => Promise<User>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
  sessionExpired: boolean;
  clearExpired: () => void;
};

const Ctx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  const [sessionExpired, setSessionExpired] = useState(false);

  const refresh = useCallback(async () => {
    if (!getToken()) {
      setUser(null);
      return;
    }
    try {
      setUser(await api<User>('/auth/me'));
    } catch {
      setToken(null);
      setUser(null);
    }
  }, []);

  useEffect(() => {
    // Hết hạn phiên (NFR-04): xóa token, báo người dùng đăng nhập lại; không tự gửi lại thao tác cũ
    setUnauthorizedHandler(() => {
      if (getToken()) setSessionExpired(true);
      setToken(null);
      setUser(null);
    });
    refresh().finally(() => setReady(true));
  }, [refresh]);

  const login = async (loginName: string, password: string) => {
    const res = await api<TokenResponse>('/auth/login', { method: 'POST', body: { login: loginName, password } });
    setToken(res.access_token);
    setUser(res.user);
    setSessionExpired(false);
    return res.user;
  };

  const logout = async () => {
    try {
      await api('/auth/logout', { method: 'POST' });
    } catch {
      /* vẫn đăng xuất ở phía trình duyệt */
    }
    setToken(null);
    setUser(null);
  };

  return (
    <Ctx.Provider
      value={{ user, ready, login, logout, refresh, sessionExpired, clearExpired: () => setSessionExpired(false) }}
    >
      {children}
    </Ctx.Provider>
  );
}

export function useAuth() {
  const v = useContext(Ctx);
  if (!v) throw new Error('useAuth phải dùng trong AuthProvider');
  return v;
}

/** Trang chủ theo vai trò sau khi đăng nhập (SCR-03). */
export function homeFor(role: Role): string {
  switch (role) {
    case 'ADMIN':
      return '/admin/users';
    case 'STAFF':
      return '/manage/sessions';
    case 'AUCTIONEER':
      return '/manage/sessions';
    default:
      return '/';
  }
}
