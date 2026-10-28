<template>
  <div class="page-stack">
    <section class="card workflow-card question-config-card">
      <div class="section-head">
        <div>
          <h2>生成配置</h2>
          <p>选择岗位、候选人与匹配结果，生成面试题和补充追问。</p>
        </div>
      </div>
      <p v-if="documentStore.error" class="error-note" role="alert">{{ documentStore.error }}</p>
      <div class="question-flow-grid">
        <label class="form-field workflow-field">
          <span>JD</span>
          <select v-model="selectedJdId">
            <option value="">请选择 JD</option>
            <option v-for="jd in documentStore.parsedJds" :key="jd.id" :value="jd.id">{{ jd.parsedContent?.title || jd.filename }}</option>
          </select>
        </label>
        <label class="form-field workflow-field">
          <span>候选人</span>
          <select v-model="selectedResumeId">
            <option value="">请选择简历</option>
            <option v-for="resume in documentStore.parsedResumes" :key="resume.id" :value="resume.id">
              {{ resume.parsedContent?.name || resume.filename }}
            </option>
          </select>
        </label>
        <label class="form-field workflow-field">
          <span>匹配结果（必选）</span>
          <select v-model="selectedMatchId">
            <option value="">请选择匹配结果</option>
            <option v-for="match in matchStore.results" :key="match.id" :value="match.id">
              {{ match.candidateName }} · {{ match.score }} 分
            </option>
          </select>
        </label>
        <label class="form-field workflow-field question-count-field">
          <span>题目数量</span>
          <input v-model.number="questionCount" type="number" min="1" max="10" />
        </label>
        <div class="question-action-panel">
          <button class="button-primary" type="button" :disabled="!canGenerate" @click="generate">
            <Plus class="app-icon" aria-hidden="true" />
            <span>开始生成</span>
          </button>
        </div>
      </div>
    </section>

    <TaskProgress
      title="试题生成进度"
      :task-id="task.taskId.value"
      :progress="task.progress.value"
      :current-step="task.currentStep.value"
      :completed-count="task.completedSteps.value.length"
      :steps="task.steps.value"
      :message="task.message.value"
      :error-reason="task.errorReason.value"
    />

    <section class="card workflow-card question-history-card">
      <div class="section-head">
        <div>
          <h2>历史试题集</h2>
          <p>每道题默认展示题目和考察点，评分标准与参考回答可展开查看。</p>
        </div>
        <button class="button-secondary" type="button" :disabled="matchStore.loading || questionStore.loading" @click="refreshQuestionSets">
          <RefreshCw class="app-icon" aria-hidden="true" />
          <span>刷新</span>
        </button>
      </div>
      <p v-if="matchStore.error || questionStore.error" class="error-note" role="alert">{{ matchStore.error || questionStore.error }}</p>
      <div v-if="(matchStore.loading || questionStore.loading) && !questionStore.questionSets.length" class="loading-state">正在加载试题集...</div>
      <EmptyState v-else-if="!questionStore.questionSets.length && !matchStore.error && !questionStore.error" title="暂无试题集" description="生成完成后会在这里展示历史记录。" />
      <div v-else-if="questionStore.questionSets.length" class="question-layout" :aria-busy="matchStore.loading || questionStore.loading">
        <aside class="history-list">
          <button
            v-for="set in questionStore.questionSets"
            :key="set.id"
            :class="{ active: selectedSet?.id === set.id }"
            :aria-pressed="selectedSet?.id === set.id"
            :title="`${set.candidateName} · ${set.jdTitle} · ${set.questionCount} 题`"
            type="button"
            @click="selectedSet = set"
          >
            <strong>{{ set.candidateName }}</strong>
            <span>{{ set.jdTitle }} · {{ set.questionCount }} 题</span>
          </button>
        </aside>
        <div v-if="selectedSet" class="question-list">
          <div class="question-list-head">
            <div>
              <h3>{{ selectedSet.candidateName }} · {{ selectedSet.jdTitle }}</h3>
              <p>{{ formatDate(selectedSet.createdAt) }}</p>
            </div>
            <button class="danger-text" type="button" @click="remove(selectedSet.id)">
              <Trash2 class="app-icon" aria-hidden="true" />
              <span>删除试题集</span>
            </button>
          </div>
          <details v-for="question in selectedSet.questions" :key="question.id" class="question-card">
            <summary>
              <strong>{{ question.title }}</strong>
              <span>{{ question.type }} · {{ question.difficulty }}</span>
              <small>{{ question.focus.join(' / ') }}</small>
            </summary>
            <div class="question-detail">
              <p><b>出题依据：</b>{{ question.evidence }}</p>
              <p><b>理想回答方向：</b>{{ question.idealAnswer }}</p>
              <p><b>评分标准：</b>{{ question.rubric.join('；') }}</p>
              <p><b>建议追问：</b>{{ question.followUps.join('；') }}</p>
            </div>
          </details>
          <div class="question-section-title">
            <div>
              <h4>追问模拟</h4>
              <p>针对经历中需要进一步确认的信息，提供补充追问。</p>
            </div>
            <span>{{ selectedSet.followUpCount }} 题</span>
          </div>
          <EmptyState
            v-if="!selectedSet.followUpQuestions.length"
            title="暂无追问模拟题"
            description="分析中发现需要进一步确认的信息时，补充追问会显示在这里。"
          />
          <details v-for="question in selectedSet.followUpQuestions" v-else :key="question.id" class="question-card followup-question-card">
            <summary>
              <strong>{{ question.title }}</strong>
              <span>{{ question.type }} · {{ question.difficulty }}</span>
              <small>{{ question.focus.join(' / ') }}</small>
            </summary>
            <div class="question-detail">
              <p><b>追问依据：</b>{{ question.evidence }}</p>
              <p><b>考察方向：</b>{{ question.idealAnswer }}</p>
              <p><b>评分参考：</b>{{ question.rubric.join('；') }}</p>
              <p><b>可继续追问：</b>{{ question.followUps.join('；') }}</p>
            </div>
          </details>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { Plus, RefreshCw, Trash2 } from '@lucide/vue'
import { computed, onMounted, ref, watch } from 'vue'
import EmptyState from '../components/EmptyState.vue'
import TaskProgress from '../components/TaskProgress.vue'
import { useTaskSse } from '../composables/useTaskSse'
import { useDocumentStore } from '../stores/document'
import { useMatchStore } from '../stores/match'
import { useQuestionStore } from '../stores/question'
import type { QuestionSet } from '../types/question'
import { QUESTION_STEPS } from '../types/task'
import { createId, formatDate } from '../utils/format'

const documentStore = useDocumentStore()
const matchStore = useMatchStore()
const questionStore = useQuestionStore()
const task = useTaskSse(QUESTION_STEPS)
const QUESTION_TASK_ID_KEY = 'resumate:active-question-task'

interface ActiveQuestionTask {
  taskId: string
  jdId: string
  resumeId: string
  matchId: string
  questionCount: number
}

const selectedJdId = ref('')
const selectedResumeId = ref('')
const selectedMatchId = ref('')
const questionCount = ref(10)
const selectedSet = ref<QuestionSet | null>(questionStore.questionSets[0] || null)
const restoredQuestionTask = ref<ActiveQuestionTask | null>(null)

const canGenerate = computed(() => Boolean(selectedJdId.value && selectedResumeId.value && selectedMatchId.value && questionCount.value >= 1 && questionCount.value <= 10 && Number.isInteger(questionCount.value) && !questionStore.loading && !matchStore.loading && task.status.value !== 'running'))

onMounted(async () => {
  await Promise.all([documentStore.loadDocuments(), matchStore.loadMatches()])
  refreshLoadedQuestionSets()
  const restored = readActiveQuestionTask()
  if (restored) {
    restoredQuestionTask.value = restored
    const restoredTaskId = restored.taskId
    task.start(restoredTaskId)
  }
})

async function refreshQuestionSets() {
  const selectedId = selectedSet.value?.id
  await matchStore.loadMatches()
  if (!matchStore.error) refreshLoadedQuestionSets(selectedId)
}

function refreshLoadedQuestionSets(selectedId = selectedSet.value?.id) {
  questionStore.loadQuestionSets(matchStore.results)
  selectedSet.value = questionStore.questionSets.find((set) => set.id === selectedId) || questionStore.questionSets[0] || null
}

watch(task.status, async (status) => {
  const restored = restoredQuestionTask.value
  if (!restored || task.taskId.value !== restored.taskId || (status !== 'success' && status !== 'failed')) return
  if (status === 'success') await restoreGeneratedQuestionSet(restored)
  localStorage.removeItem(QUESTION_TASK_ID_KEY)
  restoredQuestionTask.value = null
})

async function generate() {
  if (!canGenerate.value) return
  const jd = documentStore.parsedJds.find((item) => item.id === selectedJdId.value)
  const resume = documentStore.parsedResumes.find((item) => item.id === selectedResumeId.value)
  const match = matchStore.results.find((item) => item.id === selectedMatchId.value)
  if (!jd || !resume || !match) return
  const taskId = createId('task_questions')
  localStorage.setItem(QUESTION_TASK_ID_KEY, JSON.stringify({ taskId, jdId: jd.id, resumeId: resume.id, matchId: match.id, questionCount: questionCount.value }))
  task.start(taskId)
  try {
    await questionStore.createQuestionSet(jd, resume, questionCount.value, match, taskId)
    selectedSet.value = questionStore.questionSets[0] || null
  } catch (err) {
    task.failManual(err instanceof Error ? err.message : String(err))
  } finally {
    localStorage.removeItem(QUESTION_TASK_ID_KEY)
  }
}

async function restoreGeneratedQuestionSet(activeTask: ActiveQuestionTask) {
  const jd = documentStore.parsedJds.find((item) => item.id === activeTask.jdId)
  const resume = documentStore.parsedResumes.find((item) => item.id === activeTask.resumeId)
  const match = matchStore.results.find((item) => item.id === activeTask.matchId)
  if (!jd || !resume || !match) throw new Error('Stored question generation context no longer matches loaded records.')
  await questionStore.restoreQuestionSet(jd, resume, activeTask.questionCount, match)
  selectedSet.value = questionStore.questionSets[0] || null
}

function readActiveQuestionTask() {
  const raw = localStorage.getItem(QUESTION_TASK_ID_KEY)
  return raw ? (JSON.parse(raw) as ActiveQuestionTask) : null
}

async function remove(id: string) {
  const confirmed = window.confirm('确定删除该试题集吗？该操作不会删除 JD、简历或匹配结果。')
  if (!confirmed) return
  await questionStore.deleteQuestionSet(id)
  selectedSet.value = questionStore.questionSets[0] || null
}
</script>
