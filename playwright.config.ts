import { defineConfig, devices } from '@playwright/test'
import { mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

process.env.RESUMATE_E2E_ROOT ||= mkdtempSync(join(tmpdir(), 'resumate-e2e-'))

const frontendURL = `http://127.0.0.1:${process.env.RESUMATE_E2E_FRONTEND_PORT || '4173'}`

export default defineConfig({
  testDir: './tests/e2e',
  testIgnore: 'production-performance.spec.ts',
  fullyParallel: false,
  workers: 1,
  timeout: 45_000,
  expect: { timeout: 15_000 },
  retries: 0,
  reporter: 'list',
  use: { baseURL: frontendURL, trace: 'retain-on-failure' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: '.venv/bin/python tests/e2e/support/server.py',
    url: frontendURL,
    timeout: 90_000,
    reuseExistingServer: false,
    stdout: 'pipe',
    gracefulShutdown: { signal: 'SIGTERM', timeout: 20_000 },
  },
})
