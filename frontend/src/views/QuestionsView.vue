<template>
  <div class="page-stack">
    <section class="card">
      <div class="section-head">
        <div>
          <h2>生成配置</h2>
          <p>基于一份 JD 与一份简历生成正式面试题，不包含在线编辑和拖拽排序。</p>
        </div>
      </div>
      <div class="form-panel questions-form">
        <label>
          <span>JD</span>
          <select v-model="selectedJdId">
            <option value="">请选择 JD</option>
            <option v-for="jd in documentStore.parsedJds" :key="jd.id" :value="jd.id">{{ jd.parsedContent?.title || jd.filename }}</option>
          </select>
        </label>
        <label>
          <span>候选人</span>
          <select v-model="selectedResumeId">
            <option value="">请选择简历</option>
            <option v-for="resume in documentStore.parsedResumes" :key="resume.id" :value="resume.id">
              {{ resume.parsedContent?.name || resume.filename }}
            </option>
          </select>
        </label>
        <label>
          <span>匹配结果（必选）</span>
          <select v-model="selectedMatchId">
            <option value="">请选择匹配结果</option>
            <option v-for="match in matchStore.results" :key="match.id" :value="match.id">
              {{ match.candidateName }} · {{ match.score }} 分
            </option>
          </select>
        </label>
        <label>
          <span>题目数量</span>
          <input v-model.number="questionCount" type="number" min="1" max="10" />
        </label>
        <button class="button-primary" type="button" :disabled="!canGenerate" @click="generate">开始生成</button>
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

    <section class="card">
      <div class="section-head">
        <div>
          <h2>历史试题集</h2>
          <p>每道题默认展示题目和考察点，评分标准与参考回答可展开查看。</p>
        </div>
        <button class="button-secondary" type="button" :disabled="matchStore.loading || questionStore.loading" @click="refreshQuestionSets">刷新</button>
      </div>
      <div v-if="questionStore.loading" class="loading-state">正在加载试题集...</div>
      <EmptyState v-else-if="!questionStore.questionSets.length" title="暂无试题集" description="生成完成后会在这里展示历史记录。" />
      <div v-else class="question-layout">
        <aside class="history-list">
          <button
            v-for="set in questionStore.questionSets"
            :key="set.id"
            :class="{ active: selectedSet?.id === set.id }"
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
            <button class="danger-text" type="button" @click="remove(selectedSet.id)">删除试题集</button>
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
              <p>来自 generate_ambiguity_followups，与正式面试题分开展示。</p>
            </div>
            <span>{{ selectedSet.followUpCount }} 题</span>
          </div>
          <EmptyState
            v-if="!selectedSet.followUpQuestions.length"
            title="暂无追问模拟题"
            description="生成完成后，LLM 的 ambiguity follow-ups 会显示在这里。"
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

const canGenerate = computed(() => Boolean(selectedJdId.value && selectedResumeId.value && selectedMatchId.value && questionCount.value > 0))

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
  refreshLoadedQuestionSets(selectedId)
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
