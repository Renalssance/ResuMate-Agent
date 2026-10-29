<template><li class="tool-call"><strong>{{ label }}</strong><span>{{ statusLabel }}</span></li></template>
<script setup lang="ts">
import { computed } from 'vue'
const props = defineProps<{ name: string; status: string }>()
const names: Record<string, string> = { get_application_context: '读取岗位和简历', ask_applicant: '补充真实经历', create_resume_draft: '生成投递材料' }
const label = computed(() => names[props.name] || '处理材料')
const statusLabel = computed(() => props.status === 'completed' ? '已完成' : props.status === 'failed' ? '未完成' : props.status === 'waiting' ? '等待你回答' : props.status === 'stopped' ? '已停止' : '处理中')
</script>
<style scoped>.tool-call { display: flex; justify-content: space-between; gap: 12px; padding: 12px 0; border-bottom: 1px solid var(--color-border); } span { color: var(--color-text-secondary); }</style>
