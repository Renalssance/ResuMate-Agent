<template>
  <span :class="['status-tag', tone]">{{ label }}</span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { TaskStatus } from '../types/task'

const props = defineProps<{
  status: TaskStatus | boolean
  trueLabel?: string
  falseLabel?: string
}>()

const label = computed(() => {
  if (typeof props.status === 'boolean') return props.status ? props.trueLabel || '已完成' : props.falseLabel || '未完成'
  return {
    pending: '待处理',
    running: '处理中',
    success: '已完成',
    failed: '失败',
  }[props.status]
})

const tone = computed(() => {
  if (typeof props.status === 'boolean') return props.status ? 'success' : 'muted'
  return {
    pending: 'muted',
    running: 'info',
    success: 'success',
    failed: 'danger',
  }[props.status]
})
</script>
