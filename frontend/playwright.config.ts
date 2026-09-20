import { defineConfig } from '@playwright/test'
import { randomBytes } from 'node:crypto'

const e2ePort = process.env.FUCHENG_E2E_PORT ?? '8031'
const e2ePassword = process.env.FUCHENG_E2E_ADMIN_PASSWORD ?? randomBytes(24).toString('base64url')
process.env.FUCHENG_E2E_ADMIN_PASSWORD = e2ePassword

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  reporter: 'line',
  use: { baseURL: `http://127.0.0.1:${e2ePort}`, trace: 'off' },
  projects: [
    { name: 'desktop', use: { viewport: { width: 1440, height: 900 } } },
    { name: 'mobile', use: { viewport: { width: 390, height: 844 }, isMobile: true } },
  ],
  webServer: {
    command: 'uv run --locked python scripts/run_e2e_server.py',
    cwd: '..',
    url: `http://127.0.0.1:${e2ePort}/api/health`,
    reuseExistingServer: false,
    env: {
      FUCHENG_DATABASE_URL: process.env.FUCHENG_E2E_DATABASE_URL ?? 'sqlite:///data/public-e2e.db',
      FUCHENG_COOKIE_SECURE: 'false',
      FUCHENG_E2E_PORT: e2ePort,
      FUCHENG_E2E_ADMIN_PASSWORD: e2ePassword,
      FUCHENG_STATIC_DIR: process.env.FUCHENG_E2E_STATIC_DIR ?? 'frontend/dist-public',
      UV_CACHE_DIR: '.uv-cache',
      UV_PYTHON_INSTALL_DIR: '.uv-python',
    },
  },
})
