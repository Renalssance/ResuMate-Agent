<template>
  <article class="artifact-card">
    <div class="section-head"><h3>投递材料草稿</h3><span>第 {{ artifact.revision }} 版 · 待你核对</span></div>
    <p class="muted-note">请核对经历与表述后再使用。</p>
    <dl class="artifact-content">
      <div v-for="entry in entries" :key="entry.key">
        <dt>{{ labels[entry.key] || entry.label }}</dt><dd v-if="entry.value">{{ entry.value }}</dd>
        <dd v-for="child in entry.children" :key="child.label"><strong>{{ displayLabel(child.label) }}</strong>：{{ child.value }}</dd>
        <dd v-for="(group, index) in entry.groups" :key="index"><strong v-if="group.title">{{ group.title }}</strong><p v-if="group.value">{{ group.value }}</p><p v-for="child in group.children" :key="child.label">{{ displayLabel(child.label) }}：{{ child.value }}</p></dd>
      </div>
    </dl>
    <p class="muted-note">已引用 {{ artifact.factRefs.length }} 条已确认事实</p>
  </article>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import type { RunArtifact } from '../../api/agentRuns'
import { formatStructuredEntries } from '../../utils/structuredDisplay'
const props = defineProps<{ artifact: RunArtifact }>()
const entries = computed(() => formatStructuredEntries(props.artifact.structuredContent).map(entry => ({ ...entry, groups: entry.groups.map((group, index) => ({ ...group, title: group.title ? `${labels[entry.key] || entry.label} ${index + 1}` : '' })) })))
const labels: Record<string, string> = { summary: '个人简介', content: '材料内容', answer: '补充经历', experience: '相关经历', work_experience: '工作经历', bullets: '经历要点', target_role: '目标岗位', company: '公司', role: '岗位名称', description: '经历说明', period: '时间', highlights: '经历要点' }
function displayLabel(value: string) { return labels[value.replace(/ /g, '_')] || value }
</script>
<style scoped>.artifact-card { display: grid; gap: 16px; padding: 24px; border: 1px solid var(--color-primary-border); border-radius: var(--radius-sm); background: var(--surface-panel); } .section-head { margin-bottom: 0; } .section-head span,.muted-note { color: var(--color-text-secondary); font-size: 13px; } .artifact-content { display: grid; gap: 20px; margin: 0; overflow-wrap: anywhere; white-space: pre-wrap; } dt { font-weight: 600; margin-bottom: 8px; } dd { margin: 4px 0; line-height: 1.7; } dd p { margin: 6px 0; }</style>
