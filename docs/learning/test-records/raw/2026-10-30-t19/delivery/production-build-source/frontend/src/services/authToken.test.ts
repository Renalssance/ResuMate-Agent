import { buildAuthHeaders, requireAccessToken } from './authToken'

class MemoryStorage {
  private values = new Map<string, string>()

  getItem(key: string) {
    return this.values.get(key) ?? null
  }

  setItem(key: string, value: string) {
    this.values.set(key, value)
  }

  removeItem(key: string) {
    this.values.delete(key)
  }
}

function assert(condition: unknown, message: string) {
  if (!condition) throw new Error(message)
}

const storage = new MemoryStorage()
storage.setItem('accessToken', 'token-123')

const headers = buildAuthHeaders(storage)
assert(headers.Authorization === 'Bearer token-123', 'buildAuthHeaders should include the bearer token')
assert(requireAccessToken(storage) === 'token-123', 'requireAccessToken should return the stored token')

try {
  requireAccessToken(new MemoryStorage())
  throw new Error('requireAccessToken should fail without a stored token')
} catch (error) {
  if (!(error instanceof Error)) {
    throw new Error('missing-token error should be an Error')
  }
  assert(error.message === '请先登录后再上传 JD', 'missing-token error should tell the user to log in')
}
