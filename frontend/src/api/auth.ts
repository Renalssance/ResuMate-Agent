export interface AuthRequest {
  username: string
  password: string
  role?: 'user' | 'admin'
  admin_code?: string
}

export interface AuthResponse {
  access_token: string
  token_type: string
  username: string
  role: string
}

export interface CurrentUserResponse {
  username: string
  role: string
}

async function postAuth(endpoint: '/auth/login' | '/auth/register', payload: AuthRequest) {
  const response = await fetch(endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  const data = await response.json()
  if (!response.ok) throw new Error(data.detail || '认证请求失败')
  return data as AuthResponse
}

export function loginApi(payload: AuthRequest) {
  return postAuth('/auth/login', payload)
}

export function registerApi(payload: AuthRequest) {
  return postAuth('/auth/register', payload)
}
