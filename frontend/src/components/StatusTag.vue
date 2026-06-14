<template>
  <span :class="['status-tag', tone]">{{ label }}</span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { DocumentParseStatus } from '../types/document'
import type { TaskStatus } from '../types/task'

const props = defineProps<{
  status: TaskStatus | DocumentParseStatus | boolean
  trueLabel?: string
  falseLabel?: string
}>()

const label = computed(() => {
  if (typeof props.status === 'boolean') return props.status ? props.trueLabel || '已完成' : props.falseLabel || '未完成'
  return {
    pending: '待处理',
    running: '处理中',
    success: '已完成',
    success_with_warnings: '已完成',
    failed: '失败',
  }[props.status]
})

const tone = computed(() => {
  if (typeof props.status === 'boolean') return props.status ? 'success' : 'muted'
  return {
    pending: 'muted',
    running: 'info',
    success: 'success',
    success_with_warnings: 'info',
    failed: 'danger',
  }[props.status]
})
</script>
