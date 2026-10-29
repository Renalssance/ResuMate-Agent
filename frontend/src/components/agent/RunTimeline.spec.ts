import { mount } from '@vue/test-utils'
import { expect, it } from 'vitest'
import RunTimeline from './RunTimeline.vue'
import type { RunEvent } from '../../services/agentStream'

it.each(['succeeded', 'failed', 'cancelled'] as const)('does not present a stale in-flight percentage after %s', status => {
 const events: RunEvent[] = [
  { runId: 'r', createdAt: '2026-10-30T00:00:00Z', seq: 1, type: 'task.progress', payload: { message: 'Analysis completed', overall_progress: 50 } },
  { runId: 'r', createdAt: '2026-10-30T00:00:01Z', seq: 2, type: 'run.status', payload: { status } },
 ]
 const wrapper = mount(RunTimeline, { props: { events, status, kind: 'answer_followup' } })
 expect(wrapper.find('.current-progress').exists()).toBe(false)
 expect(wrapper.find('.phase-list').exists()).toBe(true)
})
