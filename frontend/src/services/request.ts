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
    const message = error.response?.data?.detail || error.message || '请求失败'
    return Promise.reject(new Error(message))
  },
)
