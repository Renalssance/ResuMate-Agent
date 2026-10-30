import { AxiosError } from 'axios'
import { afterEach, describe, expect, it } from 'vitest'
import { request } from './request'
const originalAdapter = request.defaults.adapter
afterEach(() => { request.defaults.adapter = originalAdapter })
function failResponse(status: number, data: unknown) { request.defaults.adapter = async config => { throw new AxiosError(`Request failed with status code ${status}`, undefined, config, undefined, { status, data, statusText: 'Error', headers: {}, config }) } }
describe('HTTP error messages', () => {
 it('preserves conflict status and the facts API message', async () => { failResponse(409, { code: 'revision_conflict', message: '事实版本已变化' }); await expect(request.get('/profile-facts/f')).rejects.toMatchObject({ status: 409, message: '事实版本已变化' }) })
 it('renders real FastAPI validation details as text', async () => { failResponse(422, { detail: [{ msg: "Input should be 'saved' or 'archived'", loc: ['query', 'status'] }] }); await expect(request.get('/jobs')).rejects.toMatchObject({ status: 422, message: "Input should be 'saved' or 'archived'" }) })
})
