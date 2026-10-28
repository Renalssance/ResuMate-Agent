import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { transform } from 'esbuild'
const source = await readFile(new URL('./auth.ts', import.meta.url), 'utf8')
const { code } = await transform(source, { loader: 'ts', format: 'esm' })
const { loginApi, registerApi } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)

// A stopped backend produces a non-JSON proxy error; users need an actionable message.
globalThis.fetch = async () => new Response('', { status: 500 })
await assert.rejects(loginApi({ username: 'preview', password: 'test' }), /暂时无法连接账号服务/)
globalThis.fetch = async () => { throw new TypeError('Failed to fetch') }
await assert.rejects(loginApi({ username: 'preview', password: 'test' }), /暂时无法连接账号服务/)
globalThis.fetch = async () => new Response(JSON.stringify({ detail: '用户名或密码错误' }), { status: 401 })
await assert.rejects(loginApi({ username: 'preview', password: 'test' }), /用户名或密码错误/)
const account = { access_token: 'test-token', token_type: 'bearer', username: 'preview', role: 'user' }
globalThis.fetch = async (url, options) => {
  assert.equal(url, '/auth/register')
  assert.equal(options?.method, 'POST')
  assert.deepEqual(JSON.parse(String(options?.body)), { username: 'preview', password: 'test' })
  return new Response(JSON.stringify(account))
}
assert.deepEqual(await registerApi({ username: 'preview', password: 'test' }), account)
console.log('Auth API: unavailable service, rejected credentials, and registration response passed.')
