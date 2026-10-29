import { defineConfig, devices } from '@playwright/test'
import { mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

process.env.RESUMATE_E2E_ROOT ||= mkdtempSync(join(tmpdir(), 'resumate-e2e-'))

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  workers: 1,
  timeout: 45_000,
  expect: { timeout: 15_000 },
  retries: 0,
  reporter: 'list',
  use: { baseURL: 'http://127.0.0.1:4173', trace: 'retain-on-failure' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: '.venv/bin/python tests/e2e/support/server.py',
    url: 'http://127.0.0.1:4173',
    timeout: 90_000,
    reuseExistingServer: false,
    stdout: 'pipe',
    gracefulShutdown: { signal: 'SIGTERM', timeout: 20_000 },
  },
})
