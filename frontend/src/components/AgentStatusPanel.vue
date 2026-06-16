<template>
  <section class="card agent-status-card">
    <div class="section-head">
      <div>
        <h2>{{ title }}</h2>
      </div>
      <span :class="['agent-status-pill', current?.level || 'info']">
        {{ current ? levelText(current.level) : 'Waiting' }}
      </span>
    </div>

    <div class="agent-current">
      <div>
        <strong>{{ current ? phaseText(current.phase) : idleText }}</strong>
        <small v-if="current">{{ elapsedText(current.timestamp) }}</small>
      </div>
    </div>

    <div v-if="events.length" class="agent-event-list">
      <article v-for="event in events" :key="`${event.timestamp}-${event.phase}-${event.attempt}`" class="agent-event-row">
        <span :class="['agent-event-dot', event.level]"></span>
        <div>
          <strong>{{ phaseText(event.phase) }}</strong>
          <small>{{ elapsedText(event.timestamp) }}</small>
        </div>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import type { AgentProgressEvent, AgentProgressLevel, AgentProgressPhase } from '../types/task'

const props = withDefaults(defineProps<{
  title: string
  taskId?: string
  current: AgentProgressEvent | null
  events: AgentProgressEvent[]
  idleText?: string
}>(), {
  taskId: '',
  idleText: '等待分析',
})

function phaseText(phase: AgentProgressPhase) {
  const labels: Record<AgentProgressPhase, string> = {
    prompt_uploading: '上传 prompt',
    waiting_response: '等待模型回复',
    validating_response: '校验结构化回复',
    reflecting: '反思重试',
    completed: '分析完成',
    failed: '分析失败',
  }
  return labels[phase]
}

function levelText(level: AgentProgressLevel) {
  const labels: Record<AgentProgressLevel, string> = {
    info: 'Running',
    success: 'Done',
    warning: 'Reflecting',
    error: 'Error',
  }
  return labels[level]
}

function elapsedText(value: string) {
  const startedAt = new Date(props.events[0]?.timestamp || value).getTime()
  const currentAt = new Date(value).getTime()
  if (Number.isNaN(startedAt) || Number.isNaN(currentAt)) return '+0s'
  const seconds = Math.max(0, Math.round((currentAt - startedAt) / 1000))
  if (seconds < 60) return `+${seconds}s`
  const minutes = Math.floor(seconds / 60)
  const remainder = seconds % 60
  return `+${minutes}m ${remainder}s`
}
</script>
