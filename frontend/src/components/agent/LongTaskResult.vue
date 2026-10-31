<template>
  <section class="saved-task-result" aria-label="本次任务结果">
    <h3>本次任务结果</h3>
    <template v-if="kind === 'document_parse' || kind === 'document_import'">
      <article v-for="document in parsedDocuments" :key="document.id">
        <strong>{{ document.filename }}</strong>
        <p>解析结果已保存，可以在文档管理查看和核对。</p>
      </article>
      <RouterLink class="result-link" to="/documents">查看文档</RouterLink>
    </template>
    <template v-else-if="kind === 'match_analysis'">
      <p>{{ matchResult.job_title }}</p>
      <ul class="saved-match-list"><li v-for="candidate in matchResult.candidates" :key="candidate.candidate_id"><span>{{ candidate.candidate_name }}</span><strong>{{ Math.round(candidate.total_score) }} 分</strong><RouterLink :to="`/matching?matchId=${matchResult.run_id}:${candidate.candidate_id}`">查看匹配报告</RouterLink></li></ul>
      <p v-if="!matchResult.candidates?.length">本次没有完成的匹配结果。</p>
    </template>
    <template v-else-if="kind === 'question_generation'">
      <p>{{ questionResult.candidate_name }} · 以下保留本次生成的题目。</p>
      <details v-for="(question, index) in questionResult.formal_questions" :key="index" class="saved-question">
        <summary>{{ index + 1 }}. {{ question.question }}</summary>
        <p><b>考察内容：</b>{{ question.assessment_points?.join('、') }}</p>
        <p><b>回答方向：</b>{{ question.reference_answer_direction }}</p>
        <p><b>评分参考：</b>{{ question.scoring_rubric?.join('；') }}</p>
        <p v-if="question.suggested_followups?.length"><b>补充追问：</b>{{ question.suggested_followups.join('；') }}</p>
      </details>
      <div v-if="questionResult.ambiguity_followups?.length"><h4>需要进一步确认</h4><p v-for="(question, index) in questionResult.ambiguity_followups" :key="index">{{ question.question }}</p></div>
      <RouterLink class="result-link" to="/questions">打开试题管理</RouterLink>
    </template>
    <template v-else-if="kind === 'answer_followup'">
      <dl class="followup-result"><dt>建议追问</dt><dd>{{ result.follow_up }}</dd><dt>追问依据</dt><dd>{{ result.reason }}</dd><dt>当前表现</dt><dd>{{ result.current_ability }}</dd><dt>下一步建议</dt><dd>{{ result.next_suggestion }}</dd></dl>
      <div v-if="evidence.length"><h4>回答中的依据</h4><ul><li v-for="item in evidence" :key="item">{{ item }}</li></ul></div>
      <div v-if="risks.length"><h4>仍需确认</h4><ul><li v-for="item in risks" :key="item">{{ item }}</li></ul></div>
    </template>
  </section>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import type { BackendDocumentParseResult } from '../../api/documents'
import type { CandidateReport, RunSummary } from '../../types/run'
const props = defineProps<{ kind: string; result: Record<string, unknown> }>()
const parsedDocuments = computed(() => (Array.isArray(props.result.documents) ? props.result.documents : [props.result]) as BackendDocumentParseResult[])
const matchResult = computed(() => props.result as unknown as RunSummary)
const questionResult = computed(() => props.result as unknown as CandidateReport)
const evidence = computed(() => (props.result.evidence || []) as string[])
const risks = computed(() => (props.result.risks || []) as string[])
</script>
<style scoped>
.saved-task-result { display: grid; gap: 16px; padding-top: 20px; border-top: 1px solid var(--color-border); min-width: 0; overflow-wrap: anywhere; line-height: 1.7; }
.saved-task-result h3,.saved-task-result h4,.saved-task-result p { margin: 0; } .saved-task-result article { display: grid; gap: 8px; }
.result-link { display: inline-flex; align-items: center; justify-self: start; min-height: 44px; color: var(--color-primary); text-underline-offset: 4px; }
.saved-match-list { display: grid; gap: 12px; padding: 0; margin: 0; list-style: none; } .saved-match-list li { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; padding: 14px; border-radius: var(--radius-sm); background: var(--surface-panel-muted); } .saved-match-list a { color: var(--color-primary); min-height: 44px; display: inline-flex; align-items: center; }
.saved-question { padding: 16px; border: 1px solid var(--color-border); border-radius: var(--radius-sm); } .saved-question summary { cursor: pointer; font-weight: 600; } .saved-question p { margin-top: 12px; }
.followup-result { display: grid; grid-template-columns: 6em minmax(0,1fr); gap: 14px 18px; margin: 0; } .followup-result dt { color: var(--color-text-secondary); } .followup-result dd { margin: 0; white-space: pre-wrap; }
@media(max-width:600px) { .followup-result { grid-template-columns: 1fr; gap: 6px; } .followup-result dd { margin-bottom: 12px; } }
</style>
