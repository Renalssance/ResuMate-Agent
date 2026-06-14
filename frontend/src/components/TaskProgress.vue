<template>
  <section v-if="taskId" class="card progress-card parse-task-list">
    <div class="progress-head">
      <div>
        <h2>{{ title }}</h2>
      </div>
    </div>

    <article class="parse-task-card" style="margin-top: 20px;">
      <div class="parse-task-head">
        <div class="parse-task-title">
          <strong>{{ currentStep || '等待任务状态' }}</strong>
        </div>
        <div class="parse-task-status">
          <strong>{{ progress }}%</strong>
        </div>
      </div>

      <div class="progress-track" aria-label="任务进度">
        <span :style="{ width: `${progress}%` }"></span>
      </div>

      <div class="parse-step-grid">
        <div
          v-for="step in steps"
          :key="step.key"
          :class="['parse-step-item', step.status]"
          :title="step.message || step.label"
        >
          <span :class="['parse-step-icon', step.status]">
            <span v-if="step.status === 'success'">✓</span>
            <span v-else-if="step.status === 'failed'">!</span>
            <span v-else-if="step.status === 'running'" class="mini-spinner"></span>
            <span v-else>·</span>
          </span>
          <div>
            <strong>{{ step.label }}</strong>
            <small>{{ stepStatusText(step) }}</small>
          </div>
        </div>
      </div>

      <p class="parse-task-message">{{ message }}</p>
      <p v-if="errorReason" class="error-note">失败原因：{{ errorReason }}</p>
    </article>
  </section>
</template>

<script setup lang="ts">
import type { ProgressStep } from '../types/task'

defineProps<{
  title: string
  taskId: string
  progress: number
  currentStep: string
  completedCount: number
  steps: ProgressStep[]
  message: string
  errorReason: string
}>()

function stepStatusText(step: ProgressStep) {
  if (step.status === 'success') return '已完成'
  if (step.status === 'failed') return '失败'
  if (step.status === 'running') {
    return step.progress > 0 ? `进行中 ${step.progress}%` : '进行中'
  }
  return '等待中'
}
</script>
