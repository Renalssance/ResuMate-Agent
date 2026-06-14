<template>
  <div v-if="document" class="drawer-layer" @click.self="$emit('close')">
    <aside class="detail-drawer">
      <header class="drawer-head">
        <div>
          <h2>{{ document.filename }}</h2>
          <p>{{ document.type === 'jd' ? 'JD 文档' : '简历文档' }} · {{ formatSize(document.size) }}</p>
        </div>
        <button class="icon-button" type="button" aria-label="关闭详情" @click="$emit('close')">×</button>
      </header>

      <div class="tab-bar">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          :class="{ active: activeTab === tab.key }"
          type="button"
          @click="activeTab = tab.key"
        >
          {{ tab.label }}
        </button>
      </div>

      <section v-if="activeTab === 'raw'" class="drawer-section">
        <h3>原始内容</h3>
        <pre>{{ document.rawText || '暂无原始文本' }}</pre>
      </section>

      <section v-else-if="activeTab === 'parsed'" class="drawer-section">
        <h3>结构化结果</h3>
        <div class="kv-grid">
          <template v-for="item in parsedItems" :key="item.key">
            <span>{{ item.key }}</span>
            <p>{{ item.value }}</p>
          </template>
        </div>
      </section>

      <section v-else class="drawer-section">
        <h3>向量与本地存储</h3>
        <div class="storage-list">
          <div>
            <span>Milvus 入库</span>
            <StatusTag :status="document.vectorized" true-label="已入库" false-label="未入库" />
          </div>
          <div>
            <span>本地保存</span>
            <StatusTag :status="document.localStored" true-label="已保存" false-label="未保存" />
          </div>
          <div>
            <span>元数据 ID</span>
            <code>{{ document.id }}</code>
          </div>
        </div>
      </section>
    </aside>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { DocumentRecord } from '../types/document'
import { formatSize } from '../utils/format'
import StatusTag from './StatusTag.vue'

const props = defineProps<{
  document: DocumentRecord | null
}>()

defineEmits<{
  close: []
}>()

const activeTab = ref('raw')
const tabs = [
  { key: 'raw', label: '原始内容' },
  { key: 'parsed', label: '结构化结果' },
  { key: 'storage', label: '向量分块' },
]

const parsedItems = computed(() => {
  const content = props.document?.parsedContent || {}
  return Object.entries(content).map(([key, value]) => ({
    key: labelMap[key] || key,
    value: Array.isArray(value) ? value.map(stringify).join('；') : stringify(value),
  }))
})

const labelMap: Record<string, string> = {
  title: '岗位名称',
  responsibilities: '岗位职责',
  requirements: '必备要求',
  bonus: '加分项',
  skills: '技能关键词',
  weights: '评价标准与权重',
  name: '基本信息',
  education: '教育经历',
  work: '工作经历',
  projects: '项目经历',
  achievements: '成果',
  ambiguities: '模糊点',
}

function stringify(value: unknown) {
  if (typeof value === 'string') return value
  if (typeof value === 'number') return String(value)
  if (value && typeof value === 'object') return JSON.stringify(value)
  return '暂无'
}
</script>
