<template>
  <section class="review-change" role="region" :aria-label="`${label}建议`">
    <div class="change-heading"><h3>{{ label }}</h3><span class="decision-badge" :class="decision.status">{{ decision.status === 'pending' && change.requires_input ? '需补充信息' : reviewLabels[decision.status] }}</span></div>
    <div class="comparison">
      <div class="original"><h4>原文</h4><p data-change-before>{{ change.before || '原文未填写' }}</p></div>
      <div class="suggestion"><h4>建议</h4><p data-change-after>{{ change.requires_input ? '补充事实后再形成建议' : change.after }}</p></div>
    </div>
    <p class="change-reason"><span>修改理由</span>{{ change.reason }}</p>
    <details v-if="references.length" class="source-details">
      <summary>查看 {{ references.length }} 条建议依据</summary>
      <ul><FactReference v-for="source in references" :key="referenceKey(source.reference)" :source="source" /></ul>
    </details>
    <div v-if="decision.status === 'edited'" class="personal-edit">
      <label :for="`edit-${change.id}`">编辑{{ label }}<span>{{ change.requires_input ? '本人补充' : '本人编辑' }}</span></label>
      <textarea :id="`edit-${change.id}`" :value="decision.editedText" rows="5" :readonly="readonly || disabled" @input="edit(($event.target as HTMLTextAreaElement).value)" />
      <p>{{ change.requires_input ? '这是你为本版本补充的信息，不会自动写入已确认事实。' : '你的表述仅用于本版本，原始建议与来源保持可查。' }}</p>
    </div>
    <div v-if="!readonly" class="decision-actions" aria-label="审阅操作">
      <button type="button" class="button-secondary" :class="{ selected: decision.status === 'accepted' }" :disabled="disabled || change.requires_input" :aria-pressed="decision.status === 'accepted'" @click="choose('accepted')">接受建议</button>
      <button type="button" class="button-secondary" :class="{ selected: decision.status === 'rejected' }" :disabled="disabled" :aria-pressed="decision.status === 'rejected'" @click="choose('rejected')">拒绝建议</button>
      <button type="button" class="button-secondary" :class="{ selected: decision.status === 'edited' }" :disabled="disabled" :aria-pressed="decision.status === 'edited'" @click="edit(decision.status === 'edited' ? decision.editedText || '' : change.after ?? change.before)">编辑内容</button>
      <button v-if="decision.status !== 'pending'" type="button" class="undo-button" :disabled="disabled" @click="choose('pending')">撤销决定</button>
    </div>
    <p v-if="decision.status === 'rejected'" class="decision-note">本版本将保留原文。</p>
  </section>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import type { ArtifactSource, ReviewDecision, ReviewStatus, TailoringChange } from '../../api/agentRuns'
import { referenceKey, reviewLabels, sectionLabel } from '../../utils/resumeReview'
import FactReference from './FactReference.vue'
const props = defineProps<{ change: TailoringChange; decision: ReviewDecision; sources: ArtifactSource[]; disabled?: boolean; readonly?: boolean }>()
const emit = defineEmits<{ decision: [value: ReviewDecision] }>()
const label = computed(() => sectionLabel(props.change.section))
const references = computed(() => { const keys = new Set(props.change.fact_refs.map(referenceKey)); return props.sources.filter(source => keys.has(referenceKey(source.reference))) })
function choose(status: ReviewStatus) { if (!props.disabled && !props.readonly && !(status === 'accepted' && props.change.requires_input)) emit('decision', { id: props.change.id, status }) }
function edit(editedText: string) { if (!props.disabled && !props.readonly) emit('decision', { id: props.change.id, status: 'edited', editedText }) }
</script>
<style scoped>
.review-change { display: grid; gap: 16px; min-width: 0; padding: 24px; background: var(--surface-panel); border: 1px solid var(--color-border); border-radius: var(--radius-sm); overflow-wrap: anywhere; }
h3, h4, p { margin: 0; }
.change-heading { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; }
h3 { font-size: 15px; line-height: 1.6; font-weight: 700; }
.decision-badge { border-radius: 6px; padding: 4px 9px; background: var(--color-bg-subtle); color: var(--color-warning); font-size: 12px; line-height: 1.4; }
.decision-badge.accepted,.decision-badge.edited { background: #edf3f6; color: var(--color-success); }
.decision-badge.rejected { color: var(--color-text-secondary); }
.comparison { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 12px; }
.comparison > div { min-width: 0; padding: 16px; border: 1px solid var(--color-border); border-radius: 8px; }
.comparison .suggestion { border-color: var(--color-primary-border); background: var(--surface-panel-soft); }
h4 { margin-bottom: 8px; font-size: 12px; color: var(--color-text-secondary); font-weight: 600; }
.comparison p { font-size: 14px; line-height: 1.85; white-space: pre-wrap; }
.change-reason { font-size: 13px; line-height: 1.8; white-space: pre-wrap; }
.change-reason > span { display: block; margin-bottom: 4px; color: var(--color-text-secondary); font-size: 12px; font-weight: 600; }
.source-details { border-top: 1px solid var(--color-border); padding-top: 12px; }
.source-details summary { cursor: pointer; color: var(--color-primary); font-size: 13px; line-height: 1.7; }
.source-details ul { display: grid; gap: 8px; padding: 0; margin: 12px 0 0; list-style: none; }
.personal-edit { display: grid; gap: 8px; }
.personal-edit label { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; font-size: 13px; font-weight: 600; }
.personal-edit label span { color: var(--color-success); font-weight: 400; font-size: 12px; }
.personal-edit textarea { width: 100%; min-height: 144px; padding: 12px; line-height: 1.8; font-size: 14px; border: 1px solid var(--color-primary-border); border-radius: 8px; background: var(--surface-inset); resize: vertical; }
.personal-edit p,.decision-note { font-size: 12px; line-height: 1.7; color: var(--color-text-secondary); }
.decision-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.decision-actions button { font-size: 13px; padding: 9px 12px; min-height: 40px; }
.decision-actions .selected { background: var(--color-primary-light); border-color: var(--color-primary-border); color: var(--color-primary); }
.undo-button { border-radius: 8px; color: var(--color-text-secondary); background: transparent; cursor: pointer; }
@media (max-width: 767px) { .review-change { padding: 16px; } .comparison { grid-template-columns: 1fr; gap: 8px; } .decision-actions button { min-height: 44px; } }
</style>
