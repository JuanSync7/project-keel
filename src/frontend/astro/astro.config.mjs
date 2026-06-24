import { defineConfig } from 'astro/config'
import tailwindcss from '@tailwindcss/vite'

// Vite blocks dev-server requests whose Host header isn't localhost. To reach
// the dev server by hostname/FQDN (e.g. when serving on 0.0.0.0 for others),
// list the host(s) in ASTRO_ALLOWED_HOSTS (comma-separated) — or "true" to
// allow any host. Kept host-neutral on purpose: no specific hostname is
// committed; the value travels in the environment, like PUBLIC_API_BASE.
const raw = process.env.ASTRO_ALLOWED_HOSTS?.trim()
const allowedHosts =
  raw === 'true'
    ? true
    : raw
      ? raw.split(',').map((h) => h.trim()).filter(Boolean)
      : []

// Same-origin API: proxy /api and /health to the backend so the browser only
// ever talks to this dev server (no cross-port reachability/CORS issues). The
// backend URL is configurable (API_PROXY_TARGET) — never hardcoded to a host.
const apiTarget = process.env.API_PROXY_TARGET?.trim() || 'http://127.0.0.1:8000'

// Site base path. A GitHub Pages *project* site serves under /<repo>/, so a
// static build needs base='/<repo>/' and every internal link/asset must respect
// it (the app uses import.meta.env.BASE_URL). Kept env-driven and host-neutral:
// the Pages workflow derives it from the repo name. Default '/' = root, which is
// right for dev, a user/org page, or a custom domain.
const base = process.env.PUBLIC_BASE_PATH?.trim() || '/'

export default defineConfig({
  base,
  vite: {
    plugins: [tailwindcss()],
    server: {
      allowedHosts,
      proxy: {
        '/api': { target: apiTarget, changeOrigin: true },
        '/health': { target: apiTarget, changeOrigin: true },
        '/llms.txt': { target: apiTarget, changeOrigin: true },
        '/llms-full.txt': { target: apiTarget, changeOrigin: true },
      },
    },
  },
})
