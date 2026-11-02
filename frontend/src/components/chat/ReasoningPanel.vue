<template>
  <details class="reasoning-panel" :open="active">
    <summary><ExecutionSpinner v-if="active" /><span>{{ active ? '正在思考' : '思考过程' }}</span><ChevronDown :size="14" class="reasoning-chevron" /></summary>
    <div ref="body" class="reasoning-content">{{ content }}</div>
  </details>
</template>

<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { ChevronDown } from '@lucide/vue'
import ExecutionSpinner from '../ExecutionSpinner.vue'
const props = defineProps<{ content: string; active: boolean }>()
const body = ref<HTMLElement | null>(null)
watch(() => props.content, async () => {
  const element = body.value
  const follow = element && element.scrollHeight - element.scrollTop - element.clientHeight < 40
  await nextTick()
  if (follow && element) element.scrollTop = element.scrollHeight
})
</script>

<style scoped>
.reasoning-panel { padding: 12px 16px; border: 1px solid rgba(158, 126, 97, .16); border-radius: 14px; background: rgba(255, 253, 249, .4); color: #8b7464; }
summary { display: flex; align-items: center; gap: 7px; cursor: pointer; list-style: none; font-size: 12px; min-height: 24px; }
summary::-webkit-details-marker { display: none; }
summary:focus-visible { outline: 2px solid #ac8965; outline-offset: 3px; }
.reasoning-chevron { margin-left: auto; }
[open] .reasoning-chevron { transform: rotate(180deg); }
.reasoning-content { max-height: 240px; overflow: auto; overscroll-behavior: contain; margin-top: 10px; white-space: pre-wrap; overflow-wrap: anywhere; font-size: 13px; line-height: 1.85; }
</style>
