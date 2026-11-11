import { fileURLToPath, URL } from 'node:url'

import tailwindcss from '@tailwindcss/vite'
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// 개발에서는 /api를 백엔드로 프록시한다(같은 오리진이라 CORS를 켜지 않는다, §9.3).
// Origin 헤더는 그대로 전달되어 백엔드의 APP_ORIGIN(http://localhost:5173)과 비교된다.
export default defineConfig({
  plugins: [vue(), tailwindcss()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    proxy: {
      '/api': { target: process.env.VITE_API_TARGET ?? 'http://127.0.0.1:8000', changeOrigin: false },
    },
  },
})
