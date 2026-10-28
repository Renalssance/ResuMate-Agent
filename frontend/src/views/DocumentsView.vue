<template>
  <div class="page-stack">
    <section class="stats-grid">
      <article class="metric-card">
        <span>JD 数量</span>
        <strong>{{ jdCount }}</strong>
      </article>
      <article class="metric-card">
        <span>简历数量</span>
        <strong>{{ resumeCount }}</strong>
      </article>
      <article class="metric-card">
        <span>已解析</span>
        <strong>{{ parsedCount }}</strong>
      </article>
      <article class="metric-card">
        <span>处理中</span>
        <strong>{{ runningCount }}</strong>
      </article>
    </section>

    <section class="card document-action-card">
      <div class="section-head">
        <div>
          <h2>上传文档</h2>
          <p>上传后自动开始解析，你可以在下方查看处理进度和结果。</p>
        </div>
      </div>

      <div class="document-workflow">
        <div class="upload-panel">
          <div class="upload-choice">
            <label class="upload-box">
              <input aria-label="上传 JD 文件" type="file" accept=".pdf,.doc,.docx,.md,.txt" @change="handleUpload('jd', $event)" />
              <FileText class="app-icon" aria-hidden="true" />
              <strong>上传 JD</strong>
              <span>支持 PDF、DOC、DOCX、TXT、MD</span>
            </label>
            <button class="button-secondary" type="button" :disabled="submittingText" @click="openTextUpload('jd')">
              <Text class="app-icon" aria-hidden="true" />
              <span>输入 JD 文本</span>
            </button>
          </div>
          <div class="upload-choice">
            <label class="upload-box">
              <input aria-label="上传简历文件" type="file" multiple accept=".pdf,.doc,.docx" @change="handleUpload('resume', $event)" />
              <FileUser class="app-icon" aria-hidden="true" />
              <strong>上传简历</strong>
              <span>可一次选择多份简历文件</span>
            </label>
            <button class="button-secondary" type="button" :disabled="submittingText" @click="openTextUpload('resume')">
              <Text class="app-icon" aria-hidden="true" />
              <span>输入简历文本</span>
            </button>
          </div>
        </div>
      </div>
      <div v-if="activeTextType" class="text-upload-panel">
        <label>
          <span>{{ activeTextType === 'jd' ? 'JD 文本' : '简历文本' }}</span>
          <textarea
            v-model="activeText"
            :disabled="submittingText"
            :placeholder="activeTextType === 'jd' ? '粘贴 JD 文本...' : '粘贴简历文本...'"
            rows="8"
          ></textarea>
        </label>
        <div class="form-actions">
          <button class="button-secondary" type="button" :disabled="submittingText" @click="activeTextType = null">
            <X class="app-icon" aria-hidden="true" />
            <span>取消</span>
          </button>
          <button class="button-primary" type="button" :disabled="!activeText.trim() || submittingText" @click="handleTextUpload">
            <Upload class="app-icon" aria-hidden="true" />
            <span>{{ submittingText ? '上传中…' : '上传文本' }}</span>
          </button>
        </div>
      </div>
    </section>

    <DocumentParseTaskList :tasks="[...parseTasks.tasks.values()]" />

    <section class="card document-list-card">
      <div class="section-head"><h2>文档列表</h2><button class="button-secondary" type="button" :disabled="store.listLoading" @click="store.loadDocuments">{{ store.listLoading ? '刷新中…' : '刷新' }}</button></div>
      <div class="tabs">
        <button v-for="tab in tabs" :key="tab.key" :class="{ active: activeTab === tab.key }" @click="activeTab = tab.key">
          {{ tab.label }}
        </button>
      </div>

      <div class="form-filter-panel filter-panel">
        <label class="form-field">
          <span>类型</span>
          <select v-model="typeFilter" class="input">
            <option value="all">全部</option>
            <option value="jd">JD</option>
            <option value="resume">简历</option>
          </select>
        </label>
        <label class="form-field">
          <span>状态</span>
          <select v-model="statusFilter" class="input">
            <option value="all">全部</option>
            <option value="pending">未解析</option>
            <option value="running">解析中</option>
            <option value="success">成功</option>
            <option value="failed">失败</option>
          </select>
        </label>
        <label class="form-field filter-search">
          <span>搜索</span>
          <input v-model="keyword" class="input" type="search" placeholder="文件名或解析内容（支持中文、拼音/首字母）" />
        </label>
      </div>

      <p v-if="store.error" class="error-note" role="alert">{{ store.error }}</p>
      <div v-if="store.listLoading && !store.documents.length" class="loading-state">正在加载文档列表...</div>
      <EmptyState
        v-else-if="!filteredDocuments.length && !store.error"
        :title="store.documents.length ? '没有符合筛选条件的文档' : '暂无文档'"
        :description="store.documents.length ? '调整类型、状态或搜索词后重试。' : '上传 JD 或简历后，解析结果会出现在这里。'"
      />
      <div v-else-if="filteredDocuments.length" class="table-wrap document-table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>文件名</th>
              <th>类型</th>
              <th>大小</th>
              <th>上传时间</th>
              <th>解析状态</th>
              <th>向量库</th>
              <th>本地保存</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="doc in filteredDocuments" :key="doc.id">
              <td data-label="文件名">
                <button class="link-button" type="button" @click="selectedDocument = doc">{{ doc.filename }}</button>
              </td>
              <td data-label="类型">{{ doc.type === 'jd' ? 'JD' : '简历' }}</td>
              <td data-label="大小">{{ formatSize(doc.size) }}</td>
              <td data-label="上传时间">{{ formatDate(doc.createdAt) }}</td>
              <td data-label="解析状态"><StatusTag :status="doc.parseStatus" /></td>
              <td data-label="向量库"><StatusTag :status="doc.vectorized" true-label="已入库" false-label="未入库" /></td>
              <td data-label="本地保存"><StatusTag :status="doc.localStored" true-label="已保存" false-label="未保存" /></td>
              <td data-label="操作">
                <div class="table-actions">
                  <button type="button" @click="selectedDocument = doc">
                    <Eye class="app-icon" aria-hidden="true" />
                    <span>查看</span>
                  </button>
                  <button type="button" :disabled="store.reparsingIds.has(doc.id)" @click="reparse(doc.id)">
                    <RefreshCw class="app-icon" aria-hidden="true" />
                    <span>重解析</span>
                  </button>
                  <button type="button" class="danger-text" :disabled="store.deletingIds.has(doc.id)" @click="remove(doc.id)">
                    <Trash2 class="app-icon" aria-hidden="true" />
                    <span>删除</span>
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <DocumentDetailDrawer :document="selectedDocument" @close="selectedDocument = null" />
  </div>
</template>

<script setup lang="ts">
import { Eye, FileText, FileUser, RefreshCw, Text, Trash2, Upload, X } from '@lucide/vue'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import DocumentDetailDrawer from '../components/DocumentDetailDrawer.vue'
import DocumentParseTaskList from '../components/DocumentParseTaskList.vue'
import EmptyState from '../components/EmptyState.vue'
import StatusTag from '../components/StatusTag.vue'
import { useDocumentParseTasks } from '../composables/useDocumentParseTasks'
import { useDocumentStore } from '../stores/document'
import {
  isDocumentParseSuccess,
  type DocumentParseStatus,
  type DocumentRecord,
  type DocumentType,
} from '../types/document'
import { formatDate, formatSize } from '../utils/format'
import { createTextUploadFile } from '../utils/textUpload'
import { buildSearchIndex, matchesSearch } from '../utils/search'

const store = useDocumentStore()
const parseTasks = useDocumentParseTasks({
  refreshDocumentsSilently: store.refreshDocumentsSilently,
  reparse: store.reparseDocument,
})
const activeTab = ref<'all' | DocumentType>('all')
const typeFilter = ref<'all' | DocumentType>('all')
const statusFilter = ref<'all' | DocumentParseStatus>('all')
const keyword = ref('')
const selectedDocument = ref<DocumentRecord | null>(null)
const activeTextType = ref<DocumentType | null>(null)
const submittingText = ref(false)
const textInputs = ref<Record<DocumentType, string>>({ jd: '', resume: '' })

const tabs = [
  { key: 'all' as const, label: '全部文档' },
  { key: 'jd' as const, label: 'JD' },
  { key: 'resume' as const, label: '简历' },
]

const searchableDocuments = computed(() => store.documents.map((doc) => ({
  doc,
  index: buildSearchIndex([doc.filename, JSON.stringify(doc.parsedContent || {})]),
})))

const filteredDocuments = computed(() => {
  return searchableDocuments.value.filter(({ doc, index }) => {
    const tabMatched = activeTab.value === 'all' || doc.type === activeTab.value
    const typeMatched = typeFilter.value === 'all' || doc.type === typeFilter.value
    const statusMatched = statusFilter.value === 'all' || (statusFilter.value === 'success' ? isDocumentParseSuccess(doc.parseStatus) : doc.parseStatus === statusFilter.value)
    const keywordMatched = matchesSearch(index, keyword.value)
    return tabMatched && typeMatched && statusMatched && keywordMatched
  }).map(({ doc }) => doc)
})

const jdCount = computed(() => store.documents.filter((doc) => doc.type === 'jd').length)
const resumeCount = computed(() => store.documents.filter((doc) => doc.type === 'resume').length)
const parsedCount = computed(() => store.documents.filter((doc) => isDocumentParseSuccess(doc.parseStatus)).length)
const runningCount = computed(() => store.documents.filter((doc) => doc.parseStatus === 'running').length)
const activeText = computed({
  get: () => (activeTextType.value ? textInputs.value[activeTextType.value] : ''),
  set: (value: string) => {
    if (activeTextType.value) textInputs.value[activeTextType.value] = value
  },
})

onMounted(store.loadDocuments)
onBeforeUnmount(parseTasks.closeAll)

async function handleUpload(type: DocumentType, event: Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files || [])
  if (!files.length) return
  await parseTasks.enqueueFiles(type, files)
  input.value = ''
}

function openTextUpload(type: DocumentType) {
  activeTextType.value = type
}

async function handleTextUpload() {
  if (!activeTextType.value || submittingText.value) return
  const type = activeTextType.value
  const file = createTextUploadFile(type, textInputs.value[type])
  submittingText.value = true
  try {
    const [succeeded] = await parseTasks.enqueueFiles(type, [file])
    if (succeeded) {
      textInputs.value[type] = ''
      activeTextType.value = null
    }
  } finally {
    submittingText.value = false
  }
}

async function reparse(id: string) {
  const document = store.documents.find((doc) => doc.id === id)
  if (document) await parseTasks.reparseDocument(document)
}

async function remove(id: string) {
  const confirmed = window.confirm('删除后将同时移除本地文件、结构化结果和 向量库数据。确定删除吗？')
  if (!confirmed) return
  await store.deleteDocument(id)
  if (selectedDocument.value?.id === id) selectedDocument.value = null
}
</script>
