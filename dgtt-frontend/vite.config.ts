import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Khi chạy dev, mọi lời gọi /api và /ws được chuyển tới backend (mặc định cổng 8000),
// nên không cần cấu hình CORS và frontend luôn gọi đường dẫn tương đối.
const BACKEND = process.env.DGTT_BACKEND ?? 'http://localhost:8000';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: BACKEND, changeOrigin: true },
      '/ws': { target: BACKEND.replace(/^http/, 'ws'), ws: true },
    },
  },
});
