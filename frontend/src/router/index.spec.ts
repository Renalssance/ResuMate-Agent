import { describe, expect, it, vi } from 'vitest'
import router from './index'

describe('lazy route views', () => {
  it('defers every route view while keeping the existing URLs and metadata', () => {
    const routes = router.options.routes
    expect(routes.map(route => route.path)).toEqual(['/', '/login', '/register', '/documents', '/chat/:sessionId?', '/interviews/:id', '/jobs', '/resume-versions/:versionId', '/agent/tasks/:runId?', '/matching', '/profile-fields', '/questions', '/applications', '/extension', '/settings'])
    for (const route of routes) {
      expect(typeof route.component, route.path).toBe('function')
      expect(route.meta?.title, route.path).toBeTruthy()
    }
    expect(router.resolve('/interviews/12').params.id).toBe('12')
    expect(router.resolve('/agent/tasks').name).toBe('agent-tasks')
    expect(router.resolve('/chat/session-1').params.sessionId).toBe('session-1')
  })
  it('loads the selected view and preserves the public layout and document title', async () => {
    const scroll = vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
    await router.push('/login')
    await vi.waitFor(() => expect(scroll).toHaveBeenCalledWith({ top: 0 }))
    vi.restoreAllMocks()
    expect(router.currentRoute.value.meta.publicLayout).toBe(true)
    expect(router.currentRoute.value.matched[0]?.components?.default).toBeTruthy()
    expect(document.title).toBe('登录 · ResuMate')
  })
})
