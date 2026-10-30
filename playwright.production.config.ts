import { defineConfig, devices } from '@playwright/test'
import { mkdtempSync } from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'

process.env.RESUMATE_E2E_ROOT ||= mkdtempSync(join(tmpdir(), 'task-17-production-browser-'))
process.env.RESUMATE_E2E_FRONTEND_PORT ||= '4273'
process.env.RESUMATE_E2E_API_PORT ||= '4274'
process.env.RESUMATE_E2E_FIXTURE_PORT ||= '8999'
process.env.RESUMATE_PRODUCTION_PORT ||= '4373'
const baseURL = `http://127.0.0.1:${process.env.RESUMATE_PRODUCTION_PORT}`

export default defineConfig({
  testDir: './tests/e2e',
  testMatch: 'production-performance.spec.ts',
  testIgnore: [],
  outputDir: join(process.env.RESUMATE_E2E_ROOT, 'browser-results'),
  fullyParallel: false, workers: 1, retries: 0, timeout: 120_000,
  expect: { timeout: 15_000 },
  reporter: [['list'], ['json', { outputFile: join(process.env.RESUMATE_E2E_ROOT, 'playwright-results.json') }]],
  use: { baseURL, trace: 'on', video: 'on' },
  projects: [{ name: 'production-chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: '.venv/bin/python tests/e2e/support/production_server.py', url: baseURL,
    timeout: 120_000, reuseExistingServer: false, stdout: 'pipe',
    gracefulShutdown: { signal: 'SIGTERM', timeout: 40_000 },
  },
})
