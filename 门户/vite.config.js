import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig(({ mode }) => ({
  plugins: [vue()],
  // GitHub Pages 子路径部署：workflow 里设置 PAGES_BASE=/ai-tutor-platform/
  base: process.env.PAGES_BASE || '/',
  define: {
    'import.meta.env.VITE_DEMO': JSON.stringify(process.env.VITE_DEMO || ''),
    'import.meta.env.VITE_LLM_PROXY': JSON.stringify(process.env.VITE_LLM_PROXY || ''),
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/admin': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/chat': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/api': {
        target: 'http://localhost:8001',
        changeOrigin: true,
      },
    },
  },
}))

