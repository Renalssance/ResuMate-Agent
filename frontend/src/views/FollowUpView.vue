<template>
  <div class="page-stack">
    <section class="card">
      <div class="section-head">
        <div>
          <h2>会话配置</h2>
          <p>最小版本仅支持单会话串行追问，不做语音、并发会话和长期记忆。</p>
        </div>
      </div>
      <div class="form-panel followup-form">
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
          <span>试题集（可选）</span>
          <select v-model="selectedQuestionSetId">
            <option value="">手动输入</option>
            <option v-for="set in questionStore.questionSets" :key="set.id" :value="set.id">
              {{ set.candidateName }} · {{ set.questionCount }} 题
            </option>
          </select>
        </label>
        <label>
          <span>初始问题</span>
          <input v-model="initialQuestion" type="text" placeholder="可手动输入第一轮问题" />
        </label>
        <button class="button-primary" type="button" :disabled="!canStart" @click="start">开始模拟</button>
      </div>
    </section>

    <TaskProgress
      title="追问生成进度"
      :task-id="task.taskId.value"
      :progress="task.progress.value"
      :current-step="task.currentStep.value"
      :completed-count="task.completedSteps.value.length"
      :steps="task.steps.value"
      :message="task.message.value"
      :error-reason="task.errorReason.value"
    />

    <section v-if="followUpStore.session" class="followup-layout">
      <aside class="card context-panel">
        <h2>候选人与岗位</h2>
        <dl>
          <dt>岗位</dt>
          <dd>{{ selectedJd?.parsedContent?.title || selectedJd?.filename }}</dd>
          <dt>候选人</dt>
          <dd>{{ selectedResume?.parsedContent?.name || selectedResume?.filename }}</dd>
          <dt>当前考察能力</dt>
          <dd>{{ followUpStore.session.currentAbility }}</dd>
        </dl>
      </aside>

      <main class="card chat-panel">
        <div class="conversation">
          <article v-for="round in followUpStore.session.rounds" :key="round.id" class="round-block">
            <div class="message agent">
              <strong>Agent 问题</strong>
              <p>{{ round.question }}</p>
            </div>
            <div v-if="round.answer" class="message candidate">
              <strong>候选人回答</strong>
              <p>{{ round.answer }}</p>
            </div>
            <div v-if="round.followUp" class="message agent">
              <strong>新追问</strong>
              <p>{{ round.followUp }}</p>
              <small>{{ round.reason }}</small>
            </div>
          </article>
        </div>
        <div class="answer-box">
          <textarea v-model="answer" placeholder="输入候选人的本轮回答"></textarea>
          <div>
            <button class="button-secondary" type="button" @click="followUpStore.appendNextRound">进入下一轮</button>
            <button class="button-primary" type="button" :disabled="!answer.trim()" @click="submit">提交回答</button>
          </div>
        </div>
      </main>

      <aside class="card evaluation-panel">
        <h2>评估摘要</h2>
        <div class="summary-block">
          <span>已识别风险</span>
          <ul>
            <li v-for="risk in latestRound?.risks || []" :key="risk">{{ risk }}</li>
          </ul>
        </div>
        <div class="summary-block">
          <span>关联简历证据</span>
          <EvidenceList :items="latestRound?.evidence || []" />
        </div>
        <div class="summary-block">
          <span>已覆盖问题</span>
          <p>{{ followUpStore.session.coveredQuestions.length }} 个</p>
        </div>
        <div class="summary-block">
          <span>下一步建议</span>
          <p>{{ followUpStore.session.nextSuggestion }}</p>
        </div>
      </aside>
    </section>

    <section v-else class="card">
      <EmptyState title="尚未开始追问模拟" description="选择 JD 与候选人后，可以启动一次单会话追问。" />
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import EmptyState from '../components/EmptyState.vue'
import EvidenceList from '../components/EvidenceList.vue'
import TaskProgress from '../components/TaskProgress.vue'
import { useTaskSse } from '../composables/useTaskSse'
import { useDocumentStore } from '../stores/document'
import { useFollowUpStore } from '../stores/followUp'
import { useQuestionStore } from '../stores/question'
import { FOLLOW_UP_STEPS } from '../types/task'
import { createId } from '../utils/format'

const documentStore = useDocumentStore()
const questionStore = useQuestionStore()
const followUpStore = useFollowUpStore()
const task = useTaskSse(FOLLOW_UP_STEPS)

const selectedJdId = ref('')
const selectedResumeId = ref('')
const selectedQuestionSetId = ref('')
const initialQuestion = ref('')
const answer = ref('')

const selectedJd = computed(() => documentStore.parsedJds.find((item) => item.id === selectedJdId.value))
const selectedResume = computed(() => documentStore.parsedResumes.find((item) => item.id === selectedResumeId.value))
const selectedQuestionSet = computed(() => questionStore.questionSets.find((item) => item.id === selectedQuestionSetId.value))
const latestRound = computed(() => followUpStore.session?.rounds.at(-1))
const canStart = computed(() => Boolean(selectedJd.value && selectedResume.value))

onMounted(() => {
  documentStore.loadDocuments()
  questionStore.loadQuestionSets()
})

function start() {
  if (!selectedJd.value || !selectedResume.value) return
  followUpStore.startSession(selectedJd.value, selectedResume.value, selectedQuestionSet.value, initialQuestion.value.trim())
  answer.value = ''
}

async function submit() {
  if (!answer.value.trim()) return
  task.startManual(createId('task_followup'), 'Backend follow-up analysis started')
  try {
    await followUpStore.submitAnswer(answer.value.trim())
    task.completeManual('Backend follow-up analysis completed')
    answer.value = ''
  } catch (err) {
    task.failManual(err instanceof Error ? err.message : String(err))
  }
}
</script>
