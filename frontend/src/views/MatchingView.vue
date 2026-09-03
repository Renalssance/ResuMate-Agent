<template>
  <div class="page-stack">
    <section class="card workflow-card matching-config-card">
      <div class="section-head">
        <div>
          <h2>匹配任务配置</h2>
          <p>仅展示解析成功的 JD 和简历，匹配过程通过 SSE 进度面板反馈。</p>
        </div>
      </div>

      <div class="matching-flow-grid">
        <div class="workflow-config-panel">
          <label class="workflow-row">
            <span>目标 JD</span>
            <select v-model="selectedJdId">
              <option value="">请选择 JD</option>
              <option v-for="jd in documentStore.parsedJds" :key="jd.id" :value="jd.id">
                {{ jd.parsedContent?.title || jd.filename }}
              </option>
            </select>
          </label>

          <label class="workflow-row">
            <span>候选人简历</span>
            <select v-model="selectedResumeIds" multiple>
              <option v-for="resume in documentStore.parsedResumes" :key="resume.id" :value="resume.id">
                {{ formatResumeLabel(resume) }}
              </option>
            </select>
          </label>
        </div>

        <div class="workflow-action-panel glass-live">
          <strong>{{ selectedResumeIds.length || 0 }}</strong>
          <span>已选择候选人</span>
          <button class="button-primary" type="button" :disabled="!canRun" @click="runMatch">开始匹配</button>
        </div>
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

    <section class="card workflow-card matching-results-card">
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
          :class="['result-card', { active: selectedResult?.id === result.id, 'glass-surface-strong': selectedResult?.id === result.id }]"
        >
          <div class="result-card-head">
            <div>
              <h3>{{ result.candidateName }}</h3>
              <p>{{ result.jdTitle }}</p>
              <p>{{ result.resumeFilename }}</p>
            </div>
            <div class="match-score" :aria-label="`匹配度 ${clampScorePercent(result.score)} 分`">
              <strong :class="scoreTone(result.score)">{{ clampScorePercent(result.score) }}</strong>
              <span>/100</span>
            </div>
          </div>
          <div class="match-score-track" aria-hidden="true">
            <span :class="scoreTone(result.score)" :style="{ width: `${clampScorePercent(result.score)}%` }"></span>
          </div>
          <p class="result-summary">{{ result.conclusion }}</p>
          <div class="compact-list">
            <span>优势：{{ result.strengths[0] }}</span>
            <span>差距：{{ result.gaps[0] }}</span>
          </div>
          <div class="card-actions">
            <button type="button" @click="showDetail(result)">
              <span class="icon-glyph view" aria-hidden="true"></span>
              <span>查看详情</span>
            </button>
            <button type="button" class="danger-text" @click="remove(result.id)">
              <span class="icon-glyph delete" aria-hidden="true"></span>
              <span>删除</span>
            </button>
          </div>
        </article>
      </div>
    </section>

    <section v-if="selectedResult" ref="detailSection" class="card workflow-card matching-detail-card">
      <div class="section-head">
        <div>
          <h2>{{ selectedResult.candidateName }} · 匹配详情</h2>
          <p>{{ selectedResult.summary }}</p>
        </div>
        <button class="button-secondary glass-action" type="button" @click="collapseDetail">
          <span class="icon-glyph close" aria-hidden="true"></span>
          <span>收起</span>
        </button>
      </div>
      <div v-if="selectedResult.warnings.length" class="warning-list">
        <p v-for="warning in selectedResult.warnings" :key="warning">{{ warning }}</p>
      </div>
      <div class="match-detail-groups" aria-label="优势、差距与风险">
        <article v-for="group in detailGroups" :key="group.key" :class="['match-detail-group', group.key]">
          <h3>{{ group.label }}</h3>
          <ul class="plain-list">
            <li v-for="item in group.items" :key="item">{{ item }}</li>
            <li v-if="!group.items.length">暂无</li>
          </ul>
        </article>
      </div>
      <details class="match-evidence-panel">
        <summary>证据引用（{{ selectedResult.evidence.length }}）</summary>
        <div v-if="selectedResult.evidence.length">
          <EvidenceList :items="selectedResult.evidence" />
        </div>
        <p v-else>暂无证据引用</p>
      </details>
      <div class="criteria-chart" aria-label="标准得分">
        <article v-for="item in criterionRows" :key="item.name" class="criterion-row">
          <div class="criterion-row-head">
            <div>
              <strong>{{ item.name }}</strong>
              <span>权重 {{ item.weight }} · 加权贡献 {{ item.contribution }}</span>
            </div>
            <b>{{ item.score }}/5</b>
          </div>
          <div class="criterion-track" :aria-label="`${item.name} 得分 ${item.score} / 5`">
            <span :class="item.tone" :style="{ width: `${item.scorePercent}%` }"></span>
          </div>
          <p>{{ item.reason }}</p>
        </article>
      </div>
      <p class="analysis-note">{{ selectedResult.agentContent }}</p>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import EmptyState from '../components/EmptyState.vue'
import EvidenceList from '../components/EvidenceList.vue'
import TaskProgress from '../components/TaskProgress.vue'
import { useTaskSse } from '../composables/useTaskSse'
import { useDocumentStore } from '../stores/document'
import { useMatchStore } from '../stores/match'
import type { MatchResult } from '../types/match'
import { MATCH_STEPS } from '../types/task'
import { createId, formatResumeLabel } from '../utils/format'
import { buildCriterionChartRows, buildMatchDetailGroups, clampScorePercent } from '../utils/matchChart'

const documentStore = useDocumentStore()
const matchStore = useMatchStore()
const task = useTaskSse(MATCH_STEPS)

const selectedJdId = ref('')
const selectedResumeIds = ref<string[]>([])
const selectedResult = ref<MatchResult | null>(matchStore.results[0] || null)
const detailSection = ref<HTMLElement | null>(null)

const canRun = computed(() => Boolean(selectedJdId.value && selectedResumeIds.value.length))
const criterionRows = computed(() => (
  selectedResult.value ? buildCriterionChartRows(selectedResult.value.criteria) : []
))
const detailGroups = computed(() => (
  selectedResult.value ? buildMatchDetailGroups(selectedResult.value) : []
))

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

async function showDetail(result: MatchResult) {
  selectedResult.value = result
  await nextTick()
  const detailTop = detailSection.value?.getBoundingClientRect().top
  if (detailTop == null) return
  window.scrollTo({
    top: Math.max(0, window.scrollY + detailTop - window.innerHeight / 2),
    behavior: 'smooth',
  })
}

function collapseDetail() {
  selectedResult.value = null
}

function scoreTone(score: number) {
  if (score >= 80) return 'score-success'
  if (score >= 65) return 'score-info'
  if (score >= 50) return 'score-warning'
  return 'score-danger'
}
</script>
