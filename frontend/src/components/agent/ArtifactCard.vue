<template>
  <article class="artifact-card">
    <div class="section-head"><h3>{{ artifact.status === 'confirmed' ? '已确认的投递材料' : '投递材料草稿' }}</h3><span>第 {{ artifact.revision }} 版 · {{ artifact.status === 'confirmed' ? '已确认' : '待你核对' }}</span></div>
    <p v-if="artifact.basedOnOldInput" class="input-notice" role="note">
      <strong>这份草稿依据旧资料生成。</strong>
      {{ changedInputNames }}已更新，以下仍保留生成时的原文与来源。
    </p>
    <template v-if="changes">
      <p class="muted-note">{{ artifact.status === 'confirmed' ? '本版本已确认，原始建议与来源保留供你核对。' : '逐条核对表述与依据，决定本版本采用的内容。' }}</p>
      <div class="change-list" aria-label="字段建议">
        <section v-for="change in changes" :key="change.id" class="change-card" :aria-label="`${sectionLabel(change.section)}建议`">
          <div class="change-head"><h4>{{ sectionLabel(change.section) }}</h4><span class="change-status" :class="{ 'needs-input': change.requires_input }">{{ change.status === 'pending' && change.requires_input ? '需补充信息' : reviewLabels[change.status] }}</span></div>
          <dl class="change-comparison">
            <div><dt>原文</dt><dd data-change-before>{{ change.before || '原文未填写' }}</dd></div>
            <div class="proposed-text"><dt>建议</dt><dd data-change-after :class="{ 'muted-note': change.requires_input }">{{ change.requires_input ? '补充事实后再形成建议' : change.after }}</dd></div>
          </dl>
          <div class="change-reason"><h5>修改理由</h5><p>{{ change.reason }}</p></div>
          <div v-if="change.fact_refs.length" class="change-sources">
            <h5>建议依据</h5>
            <ul><FactReference v-for="source in sourcesFor(change)" :key="referenceKey(source.reference)" :source="source" /></ul>
          </div>
        </section>
        <p v-if="!changes.length" class="muted-note">暂时没有字段修改建议。</p>
      </div>
    </template>
    <template v-else>
      <p class="muted-note">请核对经历与表述后再使用。</p>
      <dl class="artifact-content">
        <div v-for="entry in entries" :key="entry.key">
          <dt>{{ labels[entry.key] || entry.label }}</dt><dd v-if="entry.value">{{ entry.value }}</dd>
          <dd v-for="child in entry.children" :key="child.label"><strong>{{ displayLabel(child.label) }}</strong>：{{ child.value }}</dd>
          <dd v-for="(group, index) in entry.groups" :key="index"><strong v-if="group.title">{{ group.title }}</strong><p v-if="group.value">{{ group.value }}</p><p v-for="child in group.children" :key="child.label">{{ displayLabel(child.label) }}：{{ child.value }}</p></dd>
        </div>
      </dl>
      <p class="muted-note">已记录 {{ artifact.factRefs.length }} 条来源引用</p>
    </template>
    <RouterLink data-review-link class="button-secondary review-link" :to="`/resume-versions/${artifact.id}`">{{ artifact.status === 'confirmed' ? '查看已确认版本' : changes ? '审阅与编辑' : '查看历史材料' }}</RouterLink>
  </article>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import { reviewChanges, reviewLabels } from '../../utils/resumeReview'
import type { ArtifactReference, ResumeVersionArtifact, TailoringChange } from '../../api/agentRuns'
import FactReference from '../resume/FactReference.vue'
import { formatStructuredEntries } from '../../utils/structuredDisplay'
const props = defineProps<{ artifact: ResumeVersionArtifact }>()
const changes = computed(() => reviewChanges(props.artifact))
const entries = computed(() => formatStructuredEntries(props.artifact.structuredContent).map(entry => ({ ...entry, groups: entry.groups.map((group, index) => ({ ...group, title: group.title ? `${labels[entry.key] || entry.label} ${index + 1}` : '' })) })))
const inputLabels: Record<string, string> = { resume: '简历', jd: '岗位', facts: '已确认事实' }
const changedInputNames = computed(() => (props.artifact.changedInputs || []).map(key => inputLabels[key] || key).join('、') || '相关资料')
const labels: Record<string, string> = { self_summary: '个人简介', summary: '个人简介', content: '材料内容', answer: '补充经历', experience: '相关经历', work_experience: '工作经历', projects: '项目经历', bullets: '经历要点', target_role: '目标岗位', company: '公司', role: '岗位名称', description: '经历说明', period: '时间', highlights: '经历要点' }
function displayLabel(value: string) { return labels[value.replace(/ /g, '_')] || value }
function sectionLabel(section: string) {
  if (section === '/summary' || section === '/self_summary') return '个人简介'
  const match = /^\/(work_experience|projects)\/(\d+)\/description$/.exec(section)
  return match ? `${labels[match[1]!]} ${Number(match[2]) + 1} · 经历说明` : section
}
function referenceKey(reference: ArtifactReference) {
  if (reference.kind === 'profile_fact') return `fact:${reference.factId}:${reference.revision}`
  if (reference.kind === 'applicant_answer') return `answer:${reference.actionId}`
  return `resume:${reference.resumeId}:${reference.inputVersion}:${reference.section}`
}
function sourcesFor(change: TailoringChange) {
  const references = new Set(change.fact_refs.map(referenceKey))
  return (props.artifact.sources || []).filter(source => references.has(referenceKey(source.reference)))
}
</script>

<style scoped>
.artifact-card { display: grid; gap: 16px; min-width: 0; padding: 24px; border: 1px solid var(--color-primary-border); border-radius: var(--radius-sm); background: var(--surface-panel); overflow-wrap: anywhere; }
.section-head { margin-bottom: 0; }
.review-link { justify-self: start; text-decoration: none; }
h3, h4, h5, p { margin: 0; }
h3 { font-size: 18px; line-height: 1.5; }
.section-head span, .muted-note { color: var(--color-text-secondary); font-size: 13px; line-height: 1.7; }
.input-notice { display: grid; gap: 4px; padding: 12px 16px; border-radius: 8px; color: var(--color-warning); background: var(--color-bg-subtle); font-size: 13px; line-height: 1.7; }
.change-list { display: grid; gap: 20px; min-width: 0; }
.change-card { display: grid; gap: 16px; min-width: 0; border-top: 1px solid var(--color-border); padding-top: 20px; }
.change-head { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px 16px; }
h4 { font-size: 15px; line-height: 1.6; }
.change-status { flex-shrink: 0; border-radius: 6px; padding: 3px 8px; font-size: 12px; line-height: 1.6; color: var(--color-primary); background: var(--color-primary-light); }
.change-status.needs-input { color: var(--color-warning); background: var(--color-bg-subtle); }
.change-comparison { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; margin: 0; }
.change-comparison > div { min-width: 0; padding: 16px; border: 1px solid var(--color-border); border-radius: 8px; }
.change-comparison .proposed-text { background: var(--surface-panel-soft); border-color: var(--color-primary-border); }
.change-comparison dt, h5 { margin: 0 0 8px; color: var(--color-text-secondary); font-size: 13px; font-weight: 600; line-height: 1.6; }
.change-comparison dd { margin: 0; font-size: 14px; line-height: 1.8; white-space: pre-wrap; }
.change-reason p { font-size: 14px; line-height: 1.7; white-space: pre-wrap; }
.change-sources ul { display: grid; gap: 8px; margin: 0; padding: 0; list-style: none; }
.artifact-content { display: grid; gap: 20px; margin: 0; white-space: pre-wrap; }
.artifact-content dt { font-weight: 600; margin-bottom: 8px; }
.artifact-content dd { margin: 4px 0; line-height: 1.7; }
.artifact-content dd p { margin: 6px 0; }
@media (max-width: 767px) { .artifact-card { padding: 16px; } .change-comparison { grid-template-columns: minmax(0, 1fr); gap: 8px; } }
</style>
