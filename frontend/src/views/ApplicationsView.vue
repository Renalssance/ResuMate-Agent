<template>
  <div class="page-stack applications-page">
    <section class="stats-grid">
      <article class="metric-card application-metric total">
        <span>总投递</span>
        <strong>{{ store.totalCount }}</strong>
      </article>
      <article class="metric-card application-metric active">
        <span>流程中</span>
        <strong>{{ store.activeCount }}</strong>
      </article>
      <article class="metric-card application-metric rejected">
        <span>已挂</span>
        <strong>{{ store.rejectedCount }}</strong>
      </article>
      <article class="metric-card application-metric passed">
        <span>Offer / 通过</span>
        <strong>{{ store.passedCount }}</strong>
      </article>
    </section>

    <section class="card application-entry-card">
      <div class="section-head">
        <div>
          <h2>{{ editingId ? '编辑投递' : '新增投递' }}</h2>
          <p>记录公司、岗位、投递日期、关联简历和当前进展。</p>
        </div>
        <button v-if="editingId" class="button-secondary" type="button" @click="resetForm">
          <span class="icon-glyph close" aria-hidden="true"></span>
          <span>取消编辑</span>
        </button>
      </div>

      <form class="application-form" @submit.prevent="submitApplication">
        <label class="application-field application-company">
          <span>公司</span>
          <input v-model.trim="form.company" required placeholder="例如：字节跳动" />
        </label>
        <label class="application-field application-position">
          <span>岗位</span>
          <input v-model.trim="form.position" required placeholder="例如：后端开发工程师" />
        </label>
        <label class="application-field application-date">
          <span>投递日期</span>
          <input v-model="form.applied_date" required type="date" />
        </label>
        <label class="application-field application-status">
          <span>{{ editingId ? '当前状态' : '初始状态' }}</span>
          <select v-model="form.status" :disabled="Boolean(editingId)">
            <option v-for="item in applicationStatusOptions" :key="item.value" :value="item.value">
              {{ item.label }}
            </option>
          </select>
        </label>
        <label class="application-field application-resume">
          <span>关联简历</span>
          <select v-model="form.resume_id">
            <option :value="null">不关联</option>
            <option v-for="resume in parsedResumes" :key="resume.id" :value="resumeNumericId(resume.id)">
              {{ resume.filename }}
            </option>
          </select>
        </label>
        <label class="application-field application-link">
          <span>投递链接</span>
          <input v-model.trim="form.job_url" type="url" placeholder="https://..." />
        </label>
        <label class="application-field application-source">
          <span>来源</span>
          <input v-model.trim="form.source" placeholder="官网 / Boss / 内推 / 猎头" />
        </label>
        <label class="application-field application-notes">
          <span>备注</span>
          <input v-model.trim="form.notes" placeholder="简历版本、联系人、下一步动作等" />
        </label>
        <div class="application-field application-submit">
          <button class="button-primary" type="submit" :disabled="store.saving">
            <span :class="['icon-glyph', editingId ? 'save' : 'add']" aria-hidden="true"></span>
            <span>{{ store.saving ? '保存中...' : editingId ? '保存编辑' : '添加记录' }}</span>
          </button>
        </div>
      </form>

      <p v-if="store.error" class="error-note">{{ store.error }}</p>
    </section>

    <section class="card application-list-card">
      <div class="section-head compact">
        <div>
          <h2>投递记录</h2>
          <p>用“记录状态”追加测评、笔试、面试和结果节点。</p>
        </div>
      </div>

      <div class="application-filters">
        <label>
          <span>状态</span>
          <select v-model="statusFilter">
            <option value="all">全部</option>
            <option v-for="item in applicationStatusOptions" :key="item.value" :value="item.value">
              {{ item.label }}
            </option>
          </select>
        </label>
        <label>
          <span>搜索</span>
          <input v-model.trim="keyword" type="search" placeholder="公司、岗位、来源、备注或简历" />
        </label>
      </div>

      <div v-if="store.loading" class="loading-state">正在加载投递记录...</div>
      <EmptyState
        v-else-if="!filteredApplications.length"
        title="暂无投递记录"
        description="添加第一条投递后，这里会显示你的求职进展。"
      />
      <div v-else class="application-record-list">
        <article v-for="application in filteredApplications" :key="application.id" class="application-record">
          <div class="application-record-main">
            <div class="application-record-title">
              <strong>{{ application.company }}</strong>
              <span>{{ application.position }}</span>
            </div>
            <span :class="['application-status-pill', statusTone(application.status)]">
              {{ applicationStatusLabel(application.status) }}
            </span>
            <dl class="application-record-meta">
              <div>
                <dt>投递</dt>
                <dd>{{ formatDay(application.appliedDate) }}</dd>
              </div>
              <div>
                <dt>简历</dt>
                <dd>{{ application.resumeFilename || '未关联' }}</dd>
              </div>
              <div>
                <dt>来源</dt>
                <dd>{{ application.source || '未记录' }}</dd>
              </div>
            </dl>
            <p class="application-latest">{{ latestEventText(application) }}</p>
            <div class="application-record-actions">
              <a v-if="application.jobUrl" class="action-button" :href="application.jobUrl" target="_blank" rel="noreferrer">
                <span class="icon-glyph link" aria-hidden="true"></span>
                <span>打开</span>
              </a>
              <button class="action-button" type="button" @click="startEdit(application)">
                <span class="icon-glyph edit" aria-hidden="true"></span>
                <span>编辑</span>
              </button>
              <button class="action-button" type="button" @click="startStatusEvent(application.id)">
                <span class="icon-glyph status" aria-hidden="true"></span>
                <span>记录</span>
              </button>
              <button type="button" @click="toggleTimeline(application.id)">
                <span class="icon-glyph timeline" aria-hidden="true"></span>
                {{ expandedIds.has(application.id) ? '收起' : '时间线' }}
              </button>
              <button type="button" class="danger-text" @click="removeApplication(application.id)">
                <span class="icon-glyph delete" aria-hidden="true"></span>
                <span>删除</span>
              </button>
            </div>
          </div>

          <form
            v-if="statusDraft.applicationId === application.id"
            class="status-event-form"
            @submit.prevent="submitStatusEvent(application.id)"
          >
            <label>
              <span>新状态</span>
              <select v-model="statusDraft.status">
                <option v-for="item in applicationStatusOptions" :key="item.value" :value="item.value">
                  {{ item.label }}
                </option>
              </select>
            </label>
            <label>
              <span>发生时间</span>
              <input v-model="statusDraft.changed_at" type="datetime-local" />
            </label>
            <label>
              <span>记录</span>
              <input v-model.trim="statusDraft.note" placeholder="例如：一面已约 / 笔试完成" />
            </label>
            <button class="button-primary" type="submit">
              <span class="icon-glyph save" aria-hidden="true"></span>
              <span>保存状态</span>
            </button>
            <button class="button-secondary" type="button" @click="clearStatusDraft">
              <span class="icon-glyph close" aria-hidden="true"></span>
              <span>取消</span>
            </button>
          </form>

          <div v-if="expandedIds.has(application.id)" class="application-timeline">
            <div v-for="event in application.statusEvents" :key="event.id" class="application-timeline-item">
              <span :class="['timeline-dot', statusTone(event.status)]"></span>
              <strong>{{ applicationStatusLabel(event.status) }}</strong>
              <time>{{ formatDateTime(event.changedAt) }}</time>
              <p>{{ event.note || '无备注' }}</p>
            </div>
          </div>
        </article>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import EmptyState from '../components/EmptyState.vue'
import { useApplicationStore } from '../stores/application'
import { useDocumentStore } from '../stores/document'
import {
  applicationStatusLabel,
  applicationStatusOptions,
  type ApplicationStatus,
  type JobApplicationPayload,
  type JobApplicationRecord,
} from '../types/application'

const store = useApplicationStore()
const documentStore = useDocumentStore()
const statusFilter = ref<ApplicationStatus | 'all'>('all')
const keyword = ref('')
const editingId = ref<number | null>(null)
const expandedIds = ref<Set<number>>(new Set())
const form = reactive<JobApplicationPayload>(emptyForm())
const statusDraft = reactive({
  applicationId: null as number | null,
  status: 'assessment' as ApplicationStatus,
  changed_at: localDateTimeInput(new Date()),
  note: '',
})

const parsedResumes = computed(() => documentStore.parsedResumes)

const filteredApplications = computed(() => {
  const normalizedKeyword = keyword.value.toLowerCase()
  return store.applications.filter((application) => {
    const statusMatched = statusFilter.value === 'all' || application.status === statusFilter.value
    const keywordMatched =
      !normalizedKeyword ||
      [
        application.company,
        application.position,
        application.source,
        application.notes,
        application.resumeFilename,
      ].some((value) => value.toLowerCase().includes(normalizedKeyword))
    return statusMatched && keywordMatched
  })
})

onMounted(async () => {
  await Promise.all([store.loadApplications(), documentStore.loadDocuments()])
})

async function submitApplication() {
  if (editingId.value) {
    const { status: _status, ...payload } = form
    await store.updateApplication(editingId.value, payload)
    resetForm()
    return
  }
  await store.createApplication({ ...form })
  resetForm()
}

function startEdit(application: JobApplicationRecord) {
  editingId.value = application.id
  Object.assign(form, {
    company: application.company,
    position: application.position,
    applied_date: application.appliedDate,
    resume_id: application.resumeId,
    status: application.status,
    job_url: application.jobUrl,
    source: application.source,
    notes: application.notes,
  })
}

function resetForm() {
  editingId.value = null
  Object.assign(form, emptyForm())
}

function startStatusEvent(applicationId: number) {
  statusDraft.applicationId = applicationId
  statusDraft.status = 'assessment'
  statusDraft.changed_at = localDateTimeInput(new Date())
  statusDraft.note = ''
}

async function submitStatusEvent(applicationId: number) {
  await store.createStatusEvent(applicationId, {
    status: statusDraft.status,
    changed_at: new Date(statusDraft.changed_at).toISOString(),
    note: statusDraft.note,
  })
  clearStatusDraft()
  expandTimeline(applicationId)
}

function clearStatusDraft() {
  statusDraft.applicationId = null
  statusDraft.note = ''
}

function toggleTimeline(id: number) {
  const next = new Set(expandedIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expandedIds.value = next
}

function expandTimeline(id: number) {
  expandedIds.value = new Set(expandedIds.value).add(id)
}

async function removeApplication(id: number) {
  if (!window.confirm('确定删除这条投递记录吗？')) return
  await store.deleteApplication(id)
}

function emptyForm(): JobApplicationPayload {
  return {
    company: '',
    position: '',
    applied_date: new Date().toISOString().slice(0, 10),
    resume_id: null,
    status: 'applied',
    job_url: '',
    source: '',
    notes: '',
  }
}

function resumeNumericId(documentId: string) {
  return Number(documentId.split(':')[1] || 0)
}

function latestEventText(application: JobApplicationRecord) {
  const event = application.statusEvents[0]
  if (!event) return '无状态记录'
  return `${applicationStatusLabel(event.status)} · ${formatDateTime(event.changedAt)}${event.note ? ` · ${event.note}` : ''}`
}

function statusTone(status: ApplicationStatus) {
  if (status === 'passed' || status === 'offer') return 'success'
  if (status.includes('rejected') || status === 'withdrawn') return 'danger'
  if (status === 'applied') return 'muted'
  return 'info'
}

function formatDay(value: string) {
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date(`${value}T00:00:00`))
}

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

function localDateTimeInput(date: Date) {
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000)
  return local.toISOString().slice(0, 16)
}
</script>
