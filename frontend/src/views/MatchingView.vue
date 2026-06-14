<template>
  <div class="page-stack">
    <section class="card">
      <div class="section-head">
        <div>
          <h2>匹配任务配置</h2>
          <p>仅展示解析成功的 JD 和简历，匹配过程通过 SSE 进度面板反馈。</p>
        </div>
      </div>
      <div class="form-panel three">
        <label>
          <span>目标 JD</span>
          <select v-model="selectedJdId">
            <option value="">请选择 JD</option>
            <option v-for="jd in documentStore.parsedJds" :key="jd.id" :value="jd.id">
              {{ jd.parsedContent?.title || jd.filename }}
            </option>
          </select>
        </label>
        <label>
          <span>候选人简历</span>
          <select v-model="selectedResumeIds" multiple>
            <option v-for="resume in documentStore.parsedResumes" :key="resume.id" :value="resume.id">
              {{ resume.parsedContent?.name || resume.filename }}
            </option>
          </select>
        </label>
        <button class="button-primary" type="button" :disabled="!canRun" @click="runMatch">开始匹配</button>
      </div>
    </section>

    <TaskProgress
      title="岗位匹配进度"
      :task-id="task.taskId.value"
      :progress="task.progress.value"
      :current-step="task.currentStep.value"
      :completed-count="task.completedSteps.value.length"
      :steps="task.steps.value"
      :message="task.message.value"
      :error-reason="task.errorReason.value"
    />

    <section class="card">
      <div class="section-head">
        <div>
          <h2>匹配结果</h2>
          <p>结果仅删除匹配记录及对应向量，不影响 JD 和简历文档。</p>
        </div>
      </div>
      <div v-if="matchStore.loading" class="loading-state">正在加载匹配结果...</div>
      <EmptyState v-else-if="!matchStore.results.length" title="暂无匹配结果" description="选择 JD 与简历后开始一次匹配。" />
      <div v-else class="result-grid">
        <article
          v-for="result in matchStore.results"
          :key="result.id"
          :class="['result-card', { active: selectedResult?.id === result.id }]"
        >
          <div class="result-card-head">
            <div>
              <h3>{{ result.candidateName }}</h3>
              <p>{{ result.jdTitle }}</p>
            </div>
            <strong :class="scoreTone(result.score)">{{ result.score }}</strong>
          </div>
          <p class="result-summary">{{ result.conclusion }}</p>
          <div class="compact-list">
            <span>优势：{{ result.strengths[0] }}</span>
            <span>差距：{{ result.gaps[0] }}</span>
          </div>
          <div class="card-actions">
            <button type="button" @click="selectedResult = result">查看详情</button>
            <button type="button" class="danger-text" @click="remove(result.id)">删除</button>
          </div>
        </article>
      </div>
    </section>

    <section v-if="selectedResult" class="card">
      <div class="section-head">
        <div>
          <h2>{{ selectedResult.candidateName }} · 匹配详情</h2>
          <p>{{ selectedResult.summary }}</p>
        </div>
      </div>
      <div class="detail-columns">
        <div>
          <h3>优势、差距与风险</h3>
          <ul class="plain-list">
            <li v-for="item in selectedResult.strengths" :key="item">优势：{{ item }}</li>
            <li v-for="item in selectedResult.gaps" :key="item">差距：{{ item }}</li>
            <li v-for="item in selectedResult.risks" :key="item">风险：{{ item }}</li>
          </ul>
        </div>
        <div>
          <h3>证据引用</h3>
          <EvidenceList :items="selectedResult.evidence" />
        </div>
      </div>
      <div class="table-wrap">
        <table class="data-table compact">
          <thead>
            <tr>
              <th>标准</th>
              <th>权重</th>
              <th>得分</th>
              <th>理由</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in selectedResult.criteria" :key="item.name">
              <td>{{ item.name }}</td>
              <td>{{ item.weight }}</td>
              <td>{{ item.score }}</td>
              <td>{{ item.reason }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="analysis-note">{{ selectedResult.agentContent }}</p>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import EmptyState from '../components/EmptyState.vue'
import EvidenceList from '../components/EvidenceList.vue'
import TaskProgress from '../components/TaskProgress.vue'
import { useTaskSse } from '../composables/useTaskSse'
import { useDocumentStore } from '../stores/document'
import { useMatchStore } from '../stores/match'
import type { MatchResult } from '../types/match'
import { MATCH_STEPS } from '../types/task'
import { createId } from '../utils/format'

const documentStore = useDocumentStore()
const matchStore = useMatchStore()
const task = useTaskSse(MATCH_STEPS)

const selectedJdId = ref('')
const selectedResumeIds = ref<string[]>([])
const selectedResult = ref<MatchResult | null>(matchStore.results[0] || null)

const canRun = computed(() => Boolean(selectedJdId.value && selectedResumeIds.value.length))

onMounted(() => {
  documentStore.loadDocuments()
  matchStore.loadMatches()
})

watch(task.status, async (status) => {
  if (status !== 'success') return
  await matchStore.loadMatches()
  selectedResult.value = matchStore.results[0] || null
})

async function runMatch() {
  const jd = documentStore.parsedJds.find((item) => item.id === selectedJdId.value)
  const resumes = documentStore.parsedResumes.filter((item) => selectedResumeIds.value.includes(item.id))
  if (!jd || !resumes.length) return
  const taskId = createId('task_match')
  task.start(taskId)
  try {
    await matchStore.createMatch(jd, resumes, taskId)
    selectedResult.value = matchStore.results[0] || null
  } catch (err) {
    task.failManual(err instanceof Error ? err.message : String(err))
  }
}

async function remove(id: string) {
  const confirmed = window.confirm('仅删除该匹配结果及对应向量记录，不删除 JD 和简历。确定删除吗？')
  if (!confirmed) return
  await matchStore.deleteMatch(id)
  if (selectedResult.value?.id === id) selectedResult.value = matchStore.results[0] || null
}

function scoreTone(score: number) {
  if (score >= 80) return 'score-success'
  if (score >= 65) return 'score-info'
  if (score >= 50) return 'score-warning'
  return 'score-danger'
}
</script>
