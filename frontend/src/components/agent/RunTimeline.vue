<template>
  <div class="run-timeline">
    <h3>处理进度</h3>
    <p v-if="!phases.length" class="muted-note">正在获取任务进度</p>
    <ol v-else class="phase-list" aria-label="任务阶段"><li v-for="event in phases" :key="event.seq">{{ taskStatusLabel(event.payload.status as RunStatus, kind) || '状态已更新' }}</li></ol>
    <ul v-if="tools.length" class="tool-list" aria-label="材料处理步骤"><ToolCallCard v-for="tool in tools" :key="tool.key" :name="tool.name" :status="tool.status" /></ul>
  </div>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import { taskStatusLabel } from '../../api/agentRuns'
import type { RunEvent, RunStatus } from '../../services/agentStream'
import ToolCallCard from './ToolCallCard.vue'
const props = defineProps<{ events: RunEvent[]; status: RunStatus; kind?: string }>()
const phases = computed(() => props.events.filter(event => event.type === 'run.status'))
const tools = computed(() => {
  const values = new Map<string, { key: string; name: string; status: string }>()
  for (const event of props.events) {
    if (!event.type.startsWith('tool.')) continue
    const key = String(event.payload.operation_key), name = String(event.payload.tool_name)
    values.set(key, { key, name, status: event.type.slice(5) })
  }
  return [...values.values()].map(item => ({ ...item, status: item.status === 'started' && ['succeeded', 'failed', 'cancelled'].includes(props.status) ? 'stopped' : item.status === 'started' && item.name === 'ask_applicant' && props.status === 'waiting_input' ? 'waiting' : item.status }))
})
</script>
<style scoped>.run-timeline { display: grid; gap: 16px; } .phase-list { margin: 0; padding-left: 24px; display: grid; gap: 8px; color: var(--color-text-secondary); } .tool-list { list-style: none; padding: 0; margin: 0; } .muted-note { color: var(--color-text-secondary); }</style>
