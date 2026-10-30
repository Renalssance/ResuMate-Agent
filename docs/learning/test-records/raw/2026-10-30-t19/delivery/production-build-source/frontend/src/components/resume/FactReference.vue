<template>
  <li class="fact-reference">
    <strong class="source-label">{{ label }}</strong>
    <p class="source-content">{{ sourceText(source.content) }}</p>
    <p class="source-identity">{{ identity }}</p>
  </li>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ArtifactSource } from '../../api/agentRuns'
const props = defineProps<{ source: ArtifactSource }>()
const label = computed(() => props.source.reference.kind === 'resume'
  ? `简历 · ${sectionLabel(props.source.reference.section)}` : props.source.label)
const identity = computed(() => {
  const reference = props.source.reference
  if (reference.kind === 'profile_fact') return `事实版本：${reference.factId} · 第 ${reference.revision} 版`
  if (reference.kind === 'applicant_answer') return `补充记录：${reference.actionId}`
  return reference.sourceRefs.length ? `原文位置：${reference.sourceRefs.map(sourceText).join('、')}` : '来源：本次任务使用的简历'
})
const labels: Record<string, string> = {
  text: '事实内容', question: '补充问题', answers: '你的回答', answer: '回答',
  company: '公司', role: '岗位', title: '名称', position: '岗位', description: '经历说明',
  sourceRefs: '原文位置', source_refs: '原文位置', period: '时间', start_date: '开始时间', end_date: '结束时间',
  highlights: '经历要点', name: '名称', summary: '简介', self_summary: '个人简介',
}
function sourceText(value: unknown): string {
  if (value === null || value === undefined) return ''
  if (Array.isArray(value)) return value.map(sourceText).filter(Boolean).join('\n')
  if (typeof value === 'object') return Object.entries(value)
    .map(([key, child]) => { const text = sourceText(child); return text ? (key === 'answers' ? text : `${labels[key] || key.replace(/_/g, ' ')}：${text}`) : '' })
    .filter(Boolean).join('\n')
  return String(value)
}
function sectionLabel(section: string) {
  if (section === '/summary' || section === '/self_summary') return '个人简介'
  const match = /^\/(work_experience|projects)\/(\d+)(?:\/(.*))?$/.exec(section)
  if (match) return `${match[1] === 'work_experience' ? '工作经历' : '项目经历'} ${Number(match[2]) + 1}${match[3] ? ` · ${labels[match[3]] || match[3]}` : ''}`
  return labels[section.slice(1)] || section
}
</script>

<style scoped>
.fact-reference { display: grid; gap: 6px; min-width: 0; padding: 12px 16px; border-left: 2px solid var(--color-primary-border); background: var(--surface-panel-soft); }
.source-label { font-size: 13px; font-weight: 600; color: var(--color-primary); }
.source-content { margin: 0; font-size: 14px; line-height: 1.7; white-space: pre-wrap; overflow-wrap: anywhere; }
.source-identity { margin: 0; font-size: 12px; line-height: 1.6; color: var(--color-text-secondary); overflow-wrap: anywhere; }
</style>
