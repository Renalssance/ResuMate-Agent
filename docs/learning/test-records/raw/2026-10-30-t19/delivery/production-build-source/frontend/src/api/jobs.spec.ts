import { afterEach, describe, expect, it } from 'vitest'
import { request } from '../services/request'
import { fetchJobs } from './jobs'
const originalAdapter = request.defaults.adapter
afterEach(() => { request.defaults.adapter = originalAdapter })
describe('jobs list HTTP filtering', () => {
 it('omits empty status so the API can return jobs of all statuses', async () => {
  let uri = ''; request.defaults.adapter = async config => { uri = request.getUri(config); return { status: 200, statusText: 'OK', data: { items: [], hasMore: false }, headers: {}, config } }
  await fetchJobs({ query: '', status: '', offset: 0 }); const params = new URL(uri, 'http://localhost').searchParams
  expect(params.has('status')).toBe(false); expect(params.get('limit')).toBe('20')
 })
 it('retains a real archived filter and current page', async () => {
  let uri = ''; request.defaults.adapter = async config => { uri = request.getUri(config); return { status: 200, statusText: 'OK', data: { items: [], hasMore: false }, headers: {}, config } }
  await fetchJobs({ query: '平台', status: 'archived', offset: 20 }); const params = new URL(uri, 'http://localhost').searchParams
  expect(params.get('status')).toBe('archived'); expect(params.get('offset')).toBe('20'); expect(params.get('query')).toBe('平台')
 })
})
