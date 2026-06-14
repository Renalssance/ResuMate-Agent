<template>
  <section v-if="tasks.length" class="card progress-card">
    <div class="progress-head">
      <div>
        <h2>文档解析进度</h2>
        <p>{{ tasks.length }} 个任务</p>
      </div>
    </div>

    <div class="step-list">
      <article v-for="task in tasks" :key="task.taskId" class="task-row">
        <div class="progress-head compact">
          <div>
            <strong>{{ task.filename }}</strong>
            <small>{{ task.message }}</small>
          </div>
          <span>{{ task.overallProgress }}%</span>
        </div>
        <div class="progress-track" aria-label="文档解析进度">
          <span :style="{ width: `${task.overallProgress}%` }"></span>
        </div>
        <div class="progress-meta">
          <span>{{ stageLabel(task.stage) }}</span>
          <span v-if="task.stageProgress !== undefined">阶段 {{ task.stageProgress }}%</span>
          <span :class="['step-dot', task.status]">{{ task.status }}</span>
        </div>
        <p v-if="task.errorReason" class="error-note">失败原因：{{ task.errorReason }}</p>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import type { DocumentParseTask, ParseStage } from '../composables/useDocumentParseTasks'

defineProps<{
  tasks: DocumentParseTask[]
}>()

const labels: Record<ParseStage, string> = {
  pending: '等待中',
  upload_client: '上传中',
  server_save: '服务端保存',
  extract: '文本提取',
  llm_analyze: 'LLM 分析中',
  embedding: '向量生成',
  milvus_save: '向量入库',
  local_save: '本地保存',
  completed: '已完成',
  failed: '失败',
}

function stageLabel(stage: ParseStage) {
  return labels[stage] || stage
}
</script>
