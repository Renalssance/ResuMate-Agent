<template>
  <button
    class="profile-copy-button"
    type="button"
    :disabled="!text.trim()"
    :aria-label="accessibleLabel"
    :title="status === '复制失败' ? '无法访问剪贴板，请手动选中文字复制' : accessibleLabel"
    aria-live="polite"
    @click.prevent="copy"
  >
    <component :is="status === '已复制' ? CopyCheck : status === '复制失败' ? CopyX : Copy" class="app-icon" aria-hidden="true" />
  </button>
  <span v-if="status" class="copy-feedback" role="status">{{ status === '复制失败' ? '复制失败，请手动选中文字复制。' : status }}</span>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Copy, CopyCheck, CopyX } from '@lucide/vue'

const props = defineProps<{ value: unknown; label: string }>()
const text = computed(() => Array.isArray(props.value) ? props.value.join('\n') : String(props.value ?? ''))
const status = ref('')
const accessibleLabel = computed(() => status.value === '已复制' ? `已复制${props.label}` : status.value === '复制失败' ? `复制${props.label}失败` : `复制${props.label}`)
watch(text, () => { status.value = '' })

async function copy() {
  try {
    await navigator.clipboard.writeText(text.value)
    status.value = '已复制'
  } catch {
    status.value = '复制失败'
  }
}
</script>
