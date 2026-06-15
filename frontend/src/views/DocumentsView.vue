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

    <section class="card">
      <div class="section-head">
        <div>
          <h2>上传与筛选</h2>
          <p>上传后会立即创建解析任务，并通过统一 SSE 进度组件展示。</p>
        </div>
      </div>
      <div class="action-grid">
        <div class="upload-choice">
          <label class="upload-box">
            <input type="file" accept=".pdf,.doc,.docx,.md,.txt" @change="handleUpload('jd', $event)" />
            <strong>上传 JD</strong>
            <span>支持 PDF、DOC、DOCX、TXT、MD</span>
          </label>
          <button class="button-secondary" type="button" @click="openTextUpload('jd')">输入 JD 文本</button>
        </div>
        <div class="upload-choice">
          <label class="upload-box">
            <input type="file" multiple accept=".pdf,.doc,.docx" @change="handleUpload('resume', $event)" />
            <strong>上传简历</strong>
            <span>可一次选择多份简历文件</span>
          </label>
          <button class="button-secondary" type="button" @click="openTextUpload('resume')">输入简历文本</button>
        </div>
        <div class="filter-grid">
          <label>
            <span>类型筛选</span>
            <select v-model="typeFilter" class="input">
              <option value="all">全部</option>
              <option value="jd">JD</option>
              <option value="resume">简历</option>
            </select>
          </label>
          <label>
            <span>状态筛选</span>
            <select v-model="statusFilter" class="input">
              <option value="all">全部</option>
              <option value="pending">未解析</option>
              <option value="running">解析中</option>
              <option value="success">成功</option>
              <option value="failed">失败</option>
            </select>
          </label>
          <label>
            <span>关键词搜索</span>
            <input v-model="keyword" class="input" type="search" placeholder="文件名或解析内容" />
          </label>
        </div>
      </div>
      <div v-if="activeTextType" class="text-upload-panel">
        <label>
          <span>{{ activeTextType === 'jd' ? 'JD 文本' : '简历文本' }}</span>
          <textarea
            v-model="activeText"
            :placeholder="activeTextType === 'jd' ? '粘贴 JD 文本...' : '粘贴简历文本...'"
            rows="8"
          ></textarea>
        </label>
        <div class="text-upload-actions">
          <button class="button-primary" type="button" :disabled="!activeText.trim()" @click="handleTextUpload">
            上传文本
          </button>
          <button class="button-secondary" type="button" @click="activeTextType = null">取消</button>
        </div>
      </div>
    </section>

    <DocumentParseTaskList :tasks="[...parseTasks.tasks.values()]" />

    <section class="card">
      <div class="tabs">
        <button v-for="tab in tabs" :key="tab.key" :class="{ active: activeTab === tab.key }" @click="activeTab = tab.key">
          {{ tab.label }}
        </button>
      </div>

      <div v-if="store.listLoading && !store.documents.length" class="loading-state">正在加载文档列表...</div>
      <EmptyState
        v-else-if="!filteredDocuments.length"
        title="暂无符合条件的文档"
        description="上传 JD 或简历后，解析结果会出现在这里。"
      />
      <div v-else class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>文件名</th>
              <th>类型</th>
              <th>大小</th>
              <th>上传时间</th>
              <th>解析状态</th>
              <th>Milvus</th>
              <th>本地保存</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="doc in filteredDocuments" :key="doc.id">
              <td>
                <button class="link-button" type="button" @click="selectedDocument = doc">{{ doc.filename }}</button>
              </td>
              <td>{{ doc.type === 'jd' ? 'JD' : '简历' }}</td>
              <td>{{ formatSize(doc.size) }}</td>
              <td>{{ formatDate(doc.createdAt) }}</td>
              <td><StatusTag :status="doc.parseStatus" /></td>
              <td><StatusTag :status="doc.vectorized" true-label="已入库" false-label="未入库" /></td>
              <td><StatusTag :status="doc.localStored" true-label="已保存" false-label="未保存" /></td>
              <td>
                <div class="table-actions">
                  <button type="button" @click="selectedDocument = doc">查看</button>
                  <button type="button" @click="reparse(doc.id)">重解析</button>
                  <button type="button" class="danger-text" @click="remove(doc.id)">删除</button>
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
const textInputs = ref<Record<DocumentType, string>>({ jd: '', resume: '' })

const tabs = [
  { key: 'all' as const, label: '全部文档' },
  { key: 'jd' as const, label: 'JD' },
  { key: 'resume' as const, label: '简历' },
]

const filteredDocuments = computed(() => {
  const normalizedKeyword = keyword.value.trim().toLowerCase()
  return store.documents.filter((doc) => {
    const tabMatched = activeTab.value === 'all' || doc.type === activeTab.value
    const typeMatched = typeFilter.value === 'all' || doc.type === typeFilter.value
    const statusMatched = statusFilter.value === 'all' || (statusFilter.value === 'success' ? isDocumentParseSuccess(doc.parseStatus) : doc.parseStatus === statusFilter.value)
    const keywordMatched =
      !normalizedKeyword ||
      doc.filename.toLowerCase().includes(normalizedKeyword) ||
      JSON.stringify(doc.parsedContent || {}).toLowerCase().includes(normalizedKeyword)
    return tabMatched && typeMatched && statusMatched && keywordMatched
  })
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
  if (!activeTextType.value) return
  const type = activeTextType.value
  const file = createTextUploadFile(type, textInputs.value[type])
  await parseTasks.enqueueFiles(type, [file])
  textInputs.value[type] = ''
  activeTextType.value = null
}

async function reparse(id: string) {
  const document = store.documents.find((doc) => doc.id === id)
  if (document) await parseTasks.reparseDocument(document)
}

async function remove(id: string) {
  const confirmed = window.confirm('删除后将同时移除本地文件、结构化结果和 Milvus 向量数据。确定删除吗？')
  if (!confirmed) return
  await store.deleteDocument(id)
  if (selectedDocument.value?.id === id) selectedDocument.value = null
}
</script>
