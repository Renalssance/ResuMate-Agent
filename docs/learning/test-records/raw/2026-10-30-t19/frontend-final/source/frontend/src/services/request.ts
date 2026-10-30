import axios from 'axios'
import { buildAuthHeaders } from './authToken'

export const request = axios.create({
  baseURL: '/api',
  timeout: 300000,
})

request.interceptors.request.use((config) => {
  Object.assign(config.headers, buildAuthHeaders())
  return config
})

request.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const data = error.response?.data
    const detail = data?.detail
    const message = (Array.isArray(detail) ? detail.map(item => item.msg).filter(Boolean).join('；') : detail) || data?.message || error.message || '请求失败'
    return Promise.reject(Object.assign(new Error(message), { status: error.response?.status }))
  },
)
