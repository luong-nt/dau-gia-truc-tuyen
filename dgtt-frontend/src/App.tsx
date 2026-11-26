import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider } from './auth/AuthContext';
import { ManageLayout, PublicLayout } from './components/Layout';
import { RequireRole } from './components/ui';
import Users from './pages/admin/Users';
import { Login, Register } from './pages/Auth';
import AuctionRoom from './pages/bidder/AuctionRoom';
import MyRegistrations from './pages/bidder/MyRegistrations';
import RegistrationForm from './pages/bidder/RegistrationForm';
import Home from './pages/Home';
import Assets from './pages/manage/Assets';
import Reviews from './pages/manage/Reviews';
import SessionManage from './pages/manage/SessionManage';
import { SessionForm, SessionList } from './pages/manage/Sessions';
import Profile from './pages/Profile';
import SessionDetail from './pages/SessionDetail';

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          {/* Khu công khai và người tham gia */}
          <Route element={<PublicLayout />}>
            <Route index element={<Home />} />
            <Route path="sessions/:id" element={<SessionDetail />} />
            <Route path="login" element={<Login />} />
            <Route path="register" element={<Register />} />
            <Route path="me" element={<RequireRole><Profile /></RequireRole>} />
            <Route path="sessions/:id/register" element={<RequireRole roles={['BIDDER']}><RegistrationForm /></RequireRole>} />
            <Route path="registrations/:regId/supplement" element={<RequireRole roles={['BIDDER']}><RegistrationForm /></RequireRole>} />
            <Route path="my/registrations" element={<RequireRole roles={['BIDDER']}><MyRegistrations /></RequireRole>} />
          </Route>
          {/* Phòng đấu giá: giao diện riêng toàn màn hình */}
          <Route path="room/:id" element={<RequireRole><AuctionRoom /></RequireRole>} />
          {/* Khu quản lý */}
          <Route element={<RequireRole roles={['STAFF', 'AUCTIONEER', 'ADMIN']}><ManageLayout /></RequireRole>}>
            <Route path="manage/sessions" element={<SessionList />} />
            <Route path="manage/sessions/new" element={<RequireRole roles={['STAFF']}><SessionForm /></RequireRole>} />
            <Route path="manage/sessions/:id" element={<SessionManage />} />
            <Route path="manage/sessions/:id/edit" element={<RequireRole roles={['STAFF']}><SessionForm /></RequireRole>} />
            <Route path="manage/registrations" element={<RequireRole roles={['STAFF']}><Reviews /></RequireRole>} />
            <Route path="manage/assets" element={<RequireRole roles={['STAFF']}><Assets /></RequireRole>} />
            <Route path="admin/users" element={<RequireRole roles={['ADMIN']}><Users /></RequireRole>} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
