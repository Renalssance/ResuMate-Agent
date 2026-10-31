<template>
  <div ref="root" class="material-picker">
    <div v-if="selectedResume || selectedJob" class="material-chips">
      <button v-if="selectedResume" type="button" class="material-chip" :title="selectedResume.filename"
              :aria-label="`移除简历 ${selectedResume.filename}`" @click="emit('update:resumeId', '')">
        <FileUser :size="15" aria-hidden="true" /><span>{{ selectedResume.filename }}</span><X :size="13" aria-hidden="true" />
      </button>
      <button v-if="selectedJob" type="button" class="material-chip" :title="selectedJob.filename"
              :aria-label="`移除岗位 ${selectedJob.filename}`" @click="emit('update:jobId', '')">
        <BriefcaseBusiness :size="15" aria-hidden="true" /><span>{{ selectedJob.filename }}</span><X :size="13" aria-hidden="true" />
      </button>
    </div>
    <div class="material-anchor">
      <Transition name="material-pop">
        <section v-if="open" class="material-panel" role="dialog" aria-label="添加材料">
          <div class="source-actions">
            <button type="button" data-source-option data-source="resume" @click="section = 'resume'"><FileUser :size="18" aria-hidden="true" />选择数据库中的简历</button>
            <button type="button" data-source-option data-source="job" @click="section = 'job'"><BriefcaseBusiness :size="18" aria-hidden="true" />选择数据库中的岗位</button>
            <button type="button" data-source-option data-source="local" :disabled="busy" @click="localInput?.click()"><FileUp :size="18" aria-hidden="true" />选择本地文件</button>
          </div>
          <div v-if="section === 'resume'" class="saved-materials">
            <button v-for="item in resumes" :key="item.id" type="button" :data-resume-id="item.id" :title="item.filename"
                    @click="chooseResume(item.id)">{{ item.filename }}</button>
            <p v-if="!resumes.length">暂无已解析的简历，可选择本地文件。</p>
          </div>
          <div v-if="section === 'job'" class="saved-materials">
            <button v-for="item in jobs" :key="item.id" type="button" :data-job-id="item.id" :title="item.filename"
                    @click="chooseJob(item.id)">{{ item.parsedContent?.title || item.filename }}</button>
            <p v-if="!jobs.length">暂无已解析的岗位，可选择本地文件。</p>
          </div>
          <div v-if="pendingAction" class="type-confirmation">
            <p>{{ pendingAction.payload.reason }}</p>
            <button type="button" data-document-type="resume" @click="emit('confirm-type', 'resume')">这是简历</button>
            <button type="button" data-document-type="jd" @click="emit('confirm-type', 'jd')">这是岗位</button>
          </div>
          <p v-if="busy" role="status">正在识别文件内容…</p>
          <p v-if="importError" role="alert">{{ importError }}</p>
        </section>
      </Transition>
      <input ref="localInput" hidden type="file" accept=".pdf,.docx,.txt,.md" :disabled="busy" @change="pickLocalFile">
      <button type="button" class="material-trigger" aria-label="添加材料" aria-haspopup="dialog" :aria-expanded="open" @click="open = !open">
        <Paperclip :size="18" aria-hidden="true" />
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { BriefcaseBusiness, FileUp, FileUser, Paperclip, X } from '@lucide/vue'
import type { RunAction } from '../../api/agentRuns'
import type { ImportState } from '../../composables/useDocumentImport'
import type { DocumentRecord, DocumentType } from '../../types/document'

const props = defineProps<{
  resumes: DocumentRecord[]; jobs: DocumentRecord[]; resumeId: string; jobId: string
  importState: ImportState; pendingAction: RunAction | null; importError: string
}>()
const emit = defineEmits<{
  'update:resumeId': [id: string]; 'update:jobId': [id: string]
  'local-file': [file: File]; 'confirm-type': [type: DocumentType]
}>()
const root = ref<HTMLElement | null>(null), localInput = ref<HTMLInputElement | null>(null)
const open = ref(false), section = ref<'root' | 'resume' | 'job'>('root')
const selectedResume = computed(() => props.resumes.find(item => item.id === props.resumeId))
const selectedJob = computed(() => props.jobs.find(item => item.id === props.jobId))
const busy = computed(() => props.importState === 'uploading' || props.importState === 'processing')

function chooseResume(id: string) { emit('update:resumeId', id); open.value = false }
function chooseJob(id: string) { emit('update:jobId', id); open.value = false }
function pickLocalFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) emit('local-file', file)
  input.value = ''
}
watch(open, (value, _, onCleanup) => {
  if (!value) return
  section.value = 'root'
  const outside = (event: PointerEvent) => { if (root.value && !event.composedPath().includes(root.value)) open.value = false }
  const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') open.value = false }
  document.addEventListener('pointerdown', outside)
  document.addEventListener('keydown', escape)
  onCleanup(() => {
    document.removeEventListener('pointerdown', outside)
    document.removeEventListener('keydown', escape)
  })
})
watch(() => props.pendingAction, action => { if (action) open.value = true }, { immediate: true })
watch(() => props.importState, state => {
  if (state === 'succeeded') open.value = false
  if (state === 'failed') section.value = 'root'
})
</script>

<style scoped>
.material-picker { display: flex; align-items: center; gap: 6px; min-width: 0; color: var(--brand-cocoa, #63483e); }
.material-anchor { position: relative; flex: 0 0 38px; }
button { font: inherit; cursor: pointer; }
button:focus-visible { outline: 2px solid var(--brand-cocoa, #63483e); outline-offset: 2px; }
button:disabled { cursor: wait; opacity: .5; }
.material-trigger { width: 38px; height: 38px; padding: 0; border: 0; border-radius: 999px; color: var(--brand-muted, #786b63); background: transparent; display: grid; place-items: center; transition: color 160ms ease, background 160ms ease, transform 160ms ease; }
.material-trigger:hover, .material-trigger:focus-visible { color: var(--brand-ink, #352b27); background: color-mix(in srgb, var(--brand-cream, #faf7f2) 72%, transparent); transform: translateY(-1px); }
.material-panel { position: absolute; z-index: 20; left: 50%; bottom: calc(100% + 8px); transform: translateX(-50%); transform-origin: bottom center; box-sizing: border-box; width: min(360px, calc(100vw - 32px)); max-height: min(480px, 65dvh); overflow-y: auto; padding: 12px; border: 1px solid var(--brand-line, #ded0c2); border-radius: 20px; background: color-mix(in srgb, var(--brand-cream, #faf7f2) 88%, transparent); box-shadow: 0 18px 48px rgba(91, 66, 43, .16); backdrop-filter: blur(22px) saturate(1.08); -webkit-backdrop-filter: blur(22px) saturate(1.08); font-size: 13px; }
.source-actions { display: grid; gap: 3px; }
.source-actions button, .saved-materials button { width: 100%; min-height: 40px; padding: 9px 11px; border: 0; border-radius: 11px; color: inherit; background: transparent; text-align: left; }
.source-actions button { display: flex; align-items: center; gap: 10px; }
.source-actions button:hover:not(:disabled), .saved-materials button:hover { background: var(--color-primary-light, #f3ece4); }
.saved-materials, .type-confirmation { margin-top: 9px; padding-top: 9px; border-top: 1px solid var(--brand-line, #ded0c2); }
.saved-materials button { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.material-panel p { margin: 8px 10px; color: var(--brand-muted, #786b63); line-height: 1.6; overflow-wrap: anywhere; }
.material-panel [role="alert"] { color: var(--color-danger, #b84a4a); }
.type-confirmation button { min-height: 34px; margin: 2px 6px 2px 0; padding: 6px 12px; border: 1px solid var(--brand-line, #ded0c2); border-radius: 999px; color: inherit; background: var(--color-primary-light, #f3ece4); }
.type-confirmation button:hover { background: var(--color-bg-muted, #eee6dc); }
.material-chips { display: flex; align-items: center; flex-wrap: wrap; justify-content: flex-end; gap: 5px; min-width: 0; }
.material-chip { display: inline-flex; align-items: center; gap: 6px; min-width: 0; max-width: 150px; min-height: 30px; padding: 5px 8px; border: 1px solid var(--brand-line, #ded0c2); border-radius: 999px; color: inherit; background: color-mix(in srgb, var(--brand-cream, #faf7f2) 72%, transparent); font-size: 11px; }
.material-chip span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.material-chip svg { flex-shrink: 0; }
.material-chip:hover { background: var(--color-primary-light, #f3ece4); }
.material-pop-enter-active { transition: opacity 180ms ease, transform 180ms cubic-bezier(.2,.8,.2,1); }
.material-pop-leave-active { transition: opacity 140ms ease, transform 140ms ease; }
.material-pop-enter-from, .material-pop-leave-to { opacity: 0; transform: translate(-50%, 6px) scale(.96); }
@media (prefers-reduced-motion: reduce) {
  .material-trigger { transition: none; }
  .material-trigger:hover, .material-trigger:focus-visible { transform: none; }
  .material-pop-enter-active, .material-pop-leave-active { transition: opacity 100ms linear; }
  .material-pop-enter-from, .material-pop-leave-to { transform: translateX(-50%); }
}
</style>
