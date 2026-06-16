import { computed, ref } from 'vue'
import type { AgentProgressEvent } from '../types/task'

const taskId = ref('')
const events = ref<AgentProgressEvent[]>([])
const current = computed(() => events.value[events.value.length - 1] || null)

export function useAgentStatus() {
  function record(event: AgentProgressEvent, sourceTaskId = '') {
    if (sourceTaskId && sourceTaskId !== taskId.value) {
      events.value = []
    }
    taskId.value = sourceTaskId
    events.value = [...events.value, event].slice(-12)
  }

  function clear(sourceTaskId = '') {
    if (!sourceTaskId || sourceTaskId === taskId.value) {
      taskId.value = ''
      events.value = []
    }
  }

  return {
    taskId,
    current,
    events,
    record,
    clear,
  }
}
