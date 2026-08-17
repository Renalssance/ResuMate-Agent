import assert from 'node:assert/strict'
import { mkdtemp, rm, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import { build } from 'esbuild'

const storage = new Map()
globalThis.localStorage = {
  getItem: (key) => storage.get(key) || null,
  setItem: (key, value) => storage.set(key, String(value)),
  removeItem: (key) => storage.delete(key),
}
globalThis.window = { localStorage: globalThis.localStorage }
globalThis.fetch = async (url) => {
  assert.equal(url, '/auth/login')
  return {
    ok: true,
    json: async () => ({
      access_token: 'token-123',
      token_type: 'bearer',
      username: 'alice',
      role: 'user',
    }),
  }
}

const tempDir = await mkdtemp(join(new URL('../..', import.meta.url).pathname, '.auth-test-'))
const entry = join(tempDir, 'entry.ts')
const bundle = join(tempDir, 'entry.cjs')

try {
  await writeFile(entry, `
    export { createPinia, setActivePinia } from 'pinia'
    export { request } from ${JSON.stringify(new URL('../services/request.ts', import.meta.url).pathname)}
    export { useAuthStore } from ${JSON.stringify(new URL('./auth.ts', import.meta.url).pathname)}
    export { useDocumentStore } from ${JSON.stringify(new URL('./document.ts', import.meta.url).pathname)}
  `)
  await build({
    entryPoints: [entry],
    bundle: true,
    format: 'cjs',
    platform: 'node',
    absWorkingDir: new URL('../..', import.meta.url).pathname,
    outfile: bundle,
    logLevel: 'silent',
  })
  const { createPinia, setActivePinia, request, useAuthStore, useDocumentStore } = await import(pathToFileURL(bundle))

  request.defaults.adapter = async (config) => {
    assert.equal(config.url, '/documents')
    assert.equal(config.headers.get?.('Authorization') || config.headers.Authorization, 'Bearer token-123')
    return {
      data: [
        {
          id: 'doc-1',
          type: 'resume',
          filename: 'resume.pdf',
          size: 42,
          raw_text: 'Candidate',
          parsed_content: {},
          vectorized: true,
          local_stored: true,
          parse_status: 'success',
          created_at: '2026-08-17T00:00:00Z',
        },
      ],
      status: 200,
      statusText: 'OK',
      headers: {},
      config,
    }
  }

  setActivePinia(createPinia())
  await useAuthStore().submit('login', { username: 'alice', password: 'secret' })

  const documentStore = useDocumentStore()
  assert.equal(documentStore.documents[0]?.filename, 'resume.pdf', documentStore.error)
} finally {
  await rm(tempDir, { recursive: true, force: true })
}
