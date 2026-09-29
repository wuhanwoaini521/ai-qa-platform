import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const REACT_RUNTIME = ['/node_modules/react/', '/node_modules/react-dom/', '/node_modules/react-router'];
const I18N_RUNTIME = ['/node_modules/i18next', '/node_modules/react-i18next'];

export default defineConfig({
  plugins: [react()],
  server: {
    // Bind IPv4 explicitly. The default `localhost` resolves to ::1 first on Windows, so the
    // server listens on IPv6 loopback only and the documented http://127.0.0.1:5173 refuses
    // the connection.
    host: '127.0.0.1',
    // Fail loudly instead of silently moving to 5174: the printed dev URL and the CORS origin
    // list both name 5173, so a silent fallback produces a page whose API calls are rejected.
    strictPort: true,
    proxy: {
      '/api': {
        // Override with VITE_DEV_API_TARGET when the API does not run on the default port.
        target: process.env.VITE_DEV_API_TARGET || 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        // Split the long-lived runtime, the icon set and the translation dictionaries into their own
        // cacheable chunks; feature chunks (including the lazy Automation Studio) build on top.
        manualChunks(id: string) {
          if (id.includes('/i18n/locales/')) {
            return 'i18n-resources';
          }
          if (I18N_RUNTIME.some((prefix) => id.includes(prefix))) {
            return 'vendor';
          }
          if (REACT_RUNTIME.some((prefix) => id.includes(prefix))) {
            return 'vendor';
          }
          if (id.includes('/node_modules/lucide-react/')) {
            return 'icons';
          }
          return undefined;
        },
      },
    },
  },
});
