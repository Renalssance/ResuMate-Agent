<template>
  <details class="attachment-progress" :open="active || interrupted">
    <summary>
      <ExecutionSpinner v-if="active" />
      <Check v-else-if="complete" :size="16" class="complete-icon" />
      <FileText v-else :size="16" />
      <span class="progress-heading">{{ heading }}</span>
      <span v-if="elapsed !== null" class="elapsed">{{ active ? '已用时' : '用时' }} {{ elapsed }} 秒</span>
      <ChevronDown :size="14" class="chevron" />
    </summary>
    <div class="progress-body">
      <p class="filename">{{ filename }}</p>
      <ol class="parse-stages" aria-label="文件解析进度">
        <li v-for="step in stages" :key="step.id" :class="step.state">
          <Check v-if="step.state === 'done'" :size="14" />
          <ExecutionSpinner v-else-if="step.state === 'active'" />
          <span v-else class="stage-dot" aria-hidden="true"></span>
          <span>{{ step.label }}</span>
          <small v-if="step.id === 'extract' && pages">{{ pages.current }}/{{ pages.total }} 页</small>
        </li>
      </ol>
      <section class="analysis-process" aria-label="分析过程">
        <h4>分析过程 <span>处理摘要</span></h4>
        <ol v-if="records.length" ref="recordList">
          <li v-for="(record, index) in records" :key="record.seq || index" :class="{ latest: index === records.length - 1 }">{{ record.message }}</li>
        </ol>
        <p v-else>{{ status === 'queued' ? '文件已收到，等待开始解析。' : '正在准备解析文件。' }}</p>
      </section>
      <p v-if="active && elapsed !== null && elapsed >= 30" class="waiting-note" role="status">当前步骤耗时较长，仍在处理中。完成后会继续回答你的问题。</p>
      <p v-if="interrupted" class="interrupted-note" role="status">{{ status === 'cancelled' ? '解析已停止，已完成的步骤保留在上方。' : '解析未完成，可使用下方的重试回复继续。' }}</p>
    </div>
  </details>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { Check, ChevronDown, FileText } from '@lucide/vue'
import type { AttachmentProgress } from '../../api/chat'
import type { RunStatus } from '../../services/agentStream'
import ExecutionSpinner from '../ExecutionSpinner.vue'

const props = defineProps<{ events: AttachmentProgress[]; status: RunStatus; filename: string }>()
const latest = computed(() => props.events.at(-1))
const complete = computed(() => latest.value?.stage === 'complete')
const active = computed(() => !complete.value && ['queued', 'running'].includes(props.status) && latest.value?.data.agent?.phase !== 'failed')
const interrupted = computed(() => !complete.value && (['failed', 'cancelled'].includes(props.status) || latest.value?.data.agent?.phase === 'failed'))
const kind = computed(() => latest.value?.data.kind === 'resume' ? '简历' : latest.value?.data.kind === 'jd' ? '岗位文件' : '文件')
const heading = computed(() => complete.value ? `${kind.value}解析完成` : interrupted.value ? `${kind.value}${props.status === 'cancelled' ? '解析已停止' : '解析未完成'}` : props.status === 'queued' ? '等待解析文件' : `正在解析${kind.value}`)
const now = ref(Date.now())
let timer: ReturnType<typeof setInterval> | undefined
watch(active, value => {
  clearInterval(timer)
  now.value = Date.now()
  if (value) timer = setInterval(() => { now.value = Date.now() }, 1000)
}, { immediate: true })
onBeforeUnmount(() => clearInterval(timer))
const elapsed = computed(() => {
  if (interrupted.value) return null
  const start = Date.parse(props.events[0]?.createdAt || '')
  const end = active.value ? now.value : Date.parse(latest.value?.createdAt || '')
  return Number.isFinite(start) && Number.isFinite(end) ? Math.max(0, Math.floor((end - start) / 1000)) : null
})
const pages = computed(() => [...props.events].reverse().find(event => event.stage === 'extract' && event.total))
const stages = computed(() => {
  const all = [
    { id: 'extract', label: '读取文件内容' },
    { id: 'classify', label: '识别文件类型' },
    { id: 'llm_analyze', label: '提取关键信息' },
    { id: 'validate', label: '核对信息来源' },
    { id: 'save', label: '保存到资料库' },
  ]
  const visited = new Set(props.events.map(event => event.stage))
  const current = latest.value?.stage || 'extract'
  return all.filter(step => !complete.value || visited.has(step.id)).map(step => ({ ...step,
    state: step.id === current && !complete.value ? active.value ? 'active' : 'stopped' : visited.has(step.id) ? 'done' : 'pending',
  }))
})
// Keep each stage/attempt's latest summary, so page and model events do not flood the card.
const records = computed(() => {
  const entries = new Map<string, AttachmentProgress>()
  for (const event of props.events) {
    const agent = event.data.agent
    const key = `${event.stage}:${agent?.attempt || 0}:${agent?.phase || ''}`
    entries.delete(key)
    entries.set(key, event)
  }
  return [...entries.values()]
})
const recordList = ref<HTMLElement | null>(null)
watch(records, async () => {
  const element = recordList.value
  const follow = !element || element.scrollHeight - element.scrollTop - element.clientHeight < 40
  await nextTick()
  if (follow && recordList.value) recordList.value.scrollTop = recordList.value.scrollHeight
}, { immediate: true })
</script>

<style scoped>
.attachment-progress { min-width: 0; padding: 14px 18px; border: 1px solid rgba(158, 126, 97, .2); border-radius: 18px; background: rgba(255, 253, 249, .7); color: #705744; }
summary { display: flex; align-items: center; gap: 8px; min-height: 26px; cursor: pointer; list-style: none; font-size: 13px; }
summary::-webkit-details-marker { display: none; }
summary:focus-visible { outline: 2px solid #ac8965; outline-offset: 4px; border-radius: 4px; }
.progress-heading { font-weight: 600; }
.elapsed { margin-left: auto; color: #917761; font-size: 11px; white-space: nowrap; font-variant-numeric: tabular-nums; }
.chevron { flex-shrink: 0; margin-left: auto; }
.elapsed + .chevron { margin-left: 2px; }
[open] .chevron { transform: rotate(180deg); }
.filename { margin: 8px 0 16px; color: #927c6b; font-size: 12px; overflow-wrap: anywhere; }
.parse-stages { display: flex; flex-wrap: wrap; gap: 10px 20px; padding: 0; margin: 0 0 18px; list-style: none; }
.parse-stages li { display: flex; align-items: center; gap: 6px; font-size: 12px; }
.parse-stages .pending { color: #a18e7e; }
.parse-stages .active { color: #705039; font-weight: 600; }
.parse-stages .done, .complete-icon { color: #63816a; }
.stage-dot { width: 7px; height: 7px; margin: 0 3px; border: 1px solid currentColor; border-radius: 50%; }
.analysis-process { border-top: 1px solid rgba(158, 126, 97, .15); padding-top: 12px; }
h4 { margin: 0 0 8px; font-size: 12px; font-weight: 600; }
h4 span { margin-left: 6px; font-size: 11px; font-weight: 400; color: #9a8574; }
.analysis-process ol { list-style: none; padding: 0; margin: 0; display: grid; gap: 5px; max-height: 190px; overflow-y: auto; }
.analysis-process li, .analysis-process p { font-size: 12px; line-height: 1.75; color: #937c69; overflow-wrap: anywhere; }
.analysis-process li.latest { color: #644b39; }
.waiting-note, .interrupted-note { margin: 12px 0 0; font-size: 12px; line-height: 1.7; color: #8b6a4d; }
@media (max-width: 600px) { .attachment-progress { padding: 12px; } .parse-stages { display: grid; grid-template-columns: 1fr; gap: 9px; } }
</style>
