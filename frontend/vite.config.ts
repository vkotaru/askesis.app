import { sveltekit } from '@sveltejs/kit/vite';
import { SvelteKitPWA } from '@vite-pwa/sveltekit';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [
    sveltekit(),
    SvelteKitPWA({
      registerType: 'prompt',
      manifest: {
        name: 'Askesis',
        short_name: 'Askesis',
        description: 'Health & Fitness Tracker',
        theme_color: '#16a34a',
        background_color: '#f8fafc',
        display: 'standalone',
        scope: '/',
        start_url: '/',
        icons: [
          {
            src: '/icon-192.png',
            sizes: '192x192',
            type: 'image/png',
          },
          {
            src: '/icon-512.png',
            sizes: '512x512',
            type: 'image/png',
          },
          {
            src: '/icon-maskable.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'maskable',
          },
        ],
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,svg,png,woff2}'],
        navigateFallback: '/',
        // /auth/ must be denied too, or the service worker can answer a
        // navigation to /auth/logout from the cached shell and the request
        // never reaches the server — leaving the session cookie intact.
        navigateFallbackDenylist: [/^\/api\//, /^\/auth\//],
        // Fonts are self-hosted under /fonts and precached via globPatterns —
        // there is no external origin left to runtime-cache.
        runtimeCaching: [
          {
            urlPattern: /\/api\/photos\/file\/.*/i,
            handler: 'CacheFirst',
            options: {
              cacheName: 'progress-photos',
              expiration: { maxEntries: 200, maxAgeSeconds: 60 * 60 * 24 * 90 },
              cacheableResponse: { statuses: [0, 200] },
            },
          },
        ],
      },
    }),
  ],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      '/auth': 'http://localhost:8000',
    },
  },
});
