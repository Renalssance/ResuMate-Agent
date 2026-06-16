<template>
  <section v-if="tasks.length" class="card progress-card">
    <div class="progress-head">
      <div>
        <h2>文档解析进度</h2>
        <p>{{ tasks.length }} 个任务</p>
      </div>
    </div>

    <div class="parse-task-list">
      <article
        v-for="task in tasks"
        :key="task.taskId"
        class="parse-task-card"
      >
        <div class="parse-task-head">
          <div class="parse-task-title">
            <strong>{{ task.filename }}</strong>
            <small>
              {{ stageLabel(task.stage) }}
              <template v-if="typeof task.stageProgress === 'number'">
                · {{ task.stageProgress }}%
              </template>
            </small>
          </div>

          <div class="parse-task-status">
            <strong>{{ task.overallProgress }}%</strong>
            <StatusTag :status="task.status" />
          </div>
        </div>

        <div class="progress-track" aria-label="文档解析总体进度">
          <span :style="{ width: `${task.overallProgress}%` }"></span>
        </div>

        <div class="parse-step-grid">
          <div
            v-for="step in task.steps"
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

        <p class="parse-task-message">{{ task.message }}</p>

        <p v-if="task.errorReason" class="error-note">
          失败原因：{{ task.errorReason }}
        </p>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import StatusTag from './StatusTag.vue'
import type { ProgressStep } from '../types/task'
import type {
  DocumentParseTask,
  ParseStage,
} from '../composables/useDocumentParseTasks'

defineProps<{
  tasks: DocumentParseTask[]
}>()

const labels: Record<ParseStage, string> = {
  pending: '等待上传',
  upload_client: '文件上传',
  server_save: '服务端保存',
  extract: '文本提取',
  llm_analyze: 'LLM 结构化分析',
  embedding: '向量生成',
  milvus_save: 'Milvus 入库',
  local_save: '本地保存',
  completed: '解析完成',
  failed: '解析失败',
}

function stageLabel(stage: ParseStage) {
  return labels[stage] || stage
}

function stepStatusText(step: ProgressStep) {
  if (step.status === 'success') return '已完成'
  if (step.status === 'failed') return '失败'
  if (step.status === 'running') {
    return step.progress > 0 ? `进行中 ${step.progress}%` : '进行中'
  }
  return '等待中'
}
</script>
