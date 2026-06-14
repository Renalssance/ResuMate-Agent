<template>
  <section v-if="taskId" class="card progress-card">
    <div class="progress-head">
      <div>
        <h2>{{ title }}</h2>
        <p>{{ currentStep || '等待任务状态' }}</p>
      </div>
      <strong>{{ progress }}%</strong>
    </div>

    <div class="progress-track" aria-label="任务进度">
      <span :style="{ width: `${progress}%` }"></span>
    </div>

    <div class="step-list">
      <div v-for="step in steps" :key="step.key" class="step-row">
        <span :class="['step-dot', step.status]">{{ symbolFor(step.status) }}</span>
        <div>
          <strong>{{ step.label }}</strong>
          <small v-if="step.message">{{ step.message }}</small>
        </div>
      </div>
    </div>

    <div class="progress-meta">
      <span>完成步骤：{{ completedCount }} / {{ steps.length }}</span>
      <span>{{ message }}</span>
    </div>

    <p v-if="errorReason" class="error-note">失败原因：{{ errorReason }}</p>
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

function symbolFor(status: ProgressStep['status']) {
  if (status === 'success') return '✓'
  if (status === 'failed') return '!'
  if (status === 'running') return '●'
  return '○'
}
</script>
