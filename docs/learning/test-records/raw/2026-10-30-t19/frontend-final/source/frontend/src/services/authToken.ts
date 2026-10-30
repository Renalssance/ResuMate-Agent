export const ACCESS_TOKEN_KEY = 'accessToken'

type TokenStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>

function getStorage(storage?: TokenStorage): TokenStorage | null {
  if (storage) return storage
  if (typeof window === 'undefined') return null
  return window.localStorage
}

export function readAccessToken(storage?: TokenStorage) {
  return getStorage(storage)?.getItem(ACCESS_TOKEN_KEY) || ''
}

export function saveAccessToken(token: string, storage?: TokenStorage) {
  getStorage(storage)?.setItem(ACCESS_TOKEN_KEY, token)
}

export function clearAccessToken(storage?: TokenStorage) {
  getStorage(storage)?.removeItem(ACCESS_TOKEN_KEY)
}

export function buildAuthHeaders(storage?: TokenStorage): Record<string, string> {
  const token = readAccessToken(storage)
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export function requireAccessToken(storage?: TokenStorage) {
  const token = readAccessToken(storage)
  if (!token) throw new Error('请先登录后再上传 JD')
  return token
}
