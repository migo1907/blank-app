import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: '/app/',
  define: { __BUILD_TS__: JSON.stringify(new Date().toISOString().slice(0,16).replace('T',' ') + ' UTC') },
  build: {
    outDir: 'dist',
    rollupOptions: {
      output: {
        // Stable vendor chunks: app code changes don't invalidate the big libs,
        // so repeat loads after a deploy pull only the small app chunk.
        manualChunks: {
          vendor:   ['react', 'react-dom'],
          recharts: ['recharts'],
          icons:    ['lucide-react'],
        },
      },
    },
  },
})
