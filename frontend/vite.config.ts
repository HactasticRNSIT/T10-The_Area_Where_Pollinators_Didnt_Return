import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      // Generate the service worker (SW) and inject the precache manifest
      // automatically at build time.
      registerType: 'autoUpdate',

      // Precache the app shell — JS/CSS bundles and index.html — so the UI
      // renders immediately even with no network.
      includeAssets: ['favicon.ico', 'robots.txt'],

      manifest: {
        name: 'PolyNexus — Pollinator Intelligence',
        short_name: 'PolyNexus',
        description: 'Real-time pollinator ecosystem analysis for Indian farmers.',
        theme_color: '#0f172a',
        background_color: '#0f172a',
        display: 'standalone',
        start_url: '/',
        icons: [
          {
            src: '/pwa-192.png',
            sizes: '192x192',
            type: 'image/png',
          },
          {
            src: '/pwa-512.png',
            sizes: '512x512',
            type: 'image/png',
          },
        ],
      },

      workbox: {
        // ── App shell: precache all static assets emitted by the build ──────
        globPatterns: ['**/*.{js,css,html,ico,png,svg,woff,woff2}'],

        // ── Runtime caching ──────────────────────────────────────────────────
        runtimeCaching: [
          {
            // /analyse?zone_id=<id>&...  → NetworkFirst so live data is
            // preferred; the most-recent response is cached per zone_id so
            // the zone renders instantly offline with a "last updated" note.
            urlPattern: /\/analyse(\?.*)?$/,
            handler: 'NetworkFirst',
            options: {
              cacheName: 'analyse-cache',
              // Keep the last 30 zone responses for up to 7 days.
              expiration: {
                maxEntries: 30,
                maxAgeSeconds: 7 * 24 * 60 * 60,
              },
              // Network timeout before falling back to cache
              networkTimeoutSeconds: 10,
              cacheableResponse: {
                statuses: [200],
              },
            },
          },
          {
            // /compare  → StaleWhileRevalidate so the UI is never blank
            urlPattern: /\/compare(\?.*)?$/,
            handler: 'StaleWhileRevalidate',
            options: {
              cacheName: 'compare-cache',
              expiration: {
                maxEntries: 10,
                maxAgeSeconds: 24 * 60 * 60,
              },
              cacheableResponse: {
                statuses: [200],
              },
            },
          },
        ],
      },
    }),
  ],
  server: {
    proxy: {
      '/health':  'http://127.0.0.1:8000',
      '/zones':   'http://127.0.0.1:8000',
      '/analyse': 'http://127.0.0.1:8000',
      '/compare': 'http://127.0.0.1:8000',
      '/chat':    'http://127.0.0.1:8000',
    },
  },
})
