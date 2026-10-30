<template>
  <dialog ref="dialog" class="detail-drawer" aria-labelledby="document-detail-title" @click.self="$emit('close')" @close="$emit('close')">
    <div v-if="document" class="drawer-content">
      <header class="drawer-head">
        <div>
          <h2 id="document-detail-title">{{ document.filename }}</h2>
          <p>{{ document.type === 'jd' ? 'JD 文档' : '简历文档' }} · {{ formatSize(document.size) }}</p>
        </div>
        <button class="icon-button" type="button" aria-label="关闭详情" @click="$emit('close')"><X class="app-icon" aria-hidden="true" /></button>
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
            <span class="kv-label">{{ item.label }}</span>
            <div class="structured-value">
              <p v-if="item.value">{{ item.value }}</p>
              <div v-if="item.children.length" class="structured-tags">
                <span v-for="child in item.children" :key="child.label" class="structured-tag">
                  <strong>{{ child.label }}</strong>
                  {{ child.value }}
                </span>
              </div>
              <div v-if="item.groups.length" class="structured-groups">
                <article v-for="(group, index) in item.groups" :key="`${item.key}-${index}`" class="structured-group">
                  <strong v-if="group.title">{{ group.title }}</strong>
                  <p v-if="group.value">{{ group.value }}</p>
                  <div v-if="group.children.length" class="structured-tags">
                    <span v-for="child in group.children" :key="child.label" class="structured-tag">
                      <strong>{{ child.label }}</strong>
                      {{ child.value }}
                    </span>
                  </div>
                </article>
              </div>
            </div>
          </template>
        </div>
      </section>

      <section v-else class="drawer-section">
        <h3>向量与本地存储</h3>
        <div class="storage-list">
          <div>
            <span>向量入库</span>
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
    </div>
  </dialog>
</template>

<script setup lang="ts">
import { X } from '@lucide/vue'
import { computed, ref, watch } from 'vue'
import type { DocumentRecord } from '../types/document'
import { formatSize } from '../utils/format'
import { formatStructuredEntries } from '../utils/structuredDisplay'
import StatusTag from './StatusTag.vue'

const props = defineProps<{
  document: DocumentRecord | null
}>()

defineEmits<{
  close: []
}>()

const dialog = ref<HTMLDialogElement | null>(null)
watch(() => props.document, (value) => {
  if (value) {
    activeTab.value = 'raw'
    if (!dialog.value?.open) dialog.value?.showModal()
  } else {
    dialog.value?.close()
  }
}, { flush: 'post' })

const activeTab = ref('raw')
const tabs = [
  { key: 'raw', label: '原始内容' },
  { key: 'parsed', label: '结构化结果' },
  { key: 'storage', label: '存储状态' },
]

const parsedItems = computed(() => {
  const content = props.document?.parsedContent || {}
  return formatStructuredEntries(content)
})
</script>
