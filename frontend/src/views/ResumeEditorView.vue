<template>
  <div class="editor-page page-stack">
    <RouterLink class="back-link" :to="store.serverSnapshot ? `/agent/tasks/${store.serverSnapshot.runId}` : '/agent/tasks'">← 返回材料准备</RouterLink>
    <section v-if="!auth.isAuthenticated" class="card editor-intro"><h2>登录后查看你的简历版本</h2><p>请<RouterLink to="/login">登录</RouterLink>后继续审阅。</p></section>
    <section v-else-if="store.loading" class="card editor-intro" aria-busy="true"><h2>正在读取简历版本…</h2><p>正在加载原文、修改建议与来源依据。</p></section>
    <template v-else>
      <div v-if="store.error" class="editor-message error-message" role="alert"><p>{{ store.error }}</p><p v-if="store.dirty">你的修改仍保留在本页。</p><button v-if="!store.serverSnapshot" class="button-secondary" type="button" @click="store.loadVersion(versionId)">重新加载</button></div>
      <template v-if="store.serverSnapshot">
        <section class="card editor-intro">
          <div class="section-head"><div><p class="eyebrow">{{ confirmed ? '已确认的投递材料' : '你的专属简历版本' }}</p><h2>{{ confirmed ? '版本已确认' : '逐条审阅这份简历' }}</h2><p>{{ confirmed ? '本版本内容已冻结，原始建议与来源仍可查看。' : '核对原文与依据，选择你希望保留的表述。' }}</p></div><span class="version-stamp">第 {{ store.serverSnapshot.revision }} 版</span></div>
          <div v-if="store.reviewable" class="review-toolbar">
            <div class="review-progress"><span>{{ store.reviewedCount }} / {{ store.changes.length }} 项已审阅</span><span v-if="store.dirty" class="unsaved-state">有未保存修改</span><span v-else>{{ confirmed ? '已确认' : '已保存' }}</span></div>
            <div v-if="!confirmed" class="save-actions"><button class="button-secondary" type="button" :disabled="!store.canSave" @click="store.save()">{{ store.busy ? '处理中…' : '保存草稿' }}</button><button class="button-primary" type="button" :disabled="!store.canConfirm" @click="store.confirm()">确认版本</button></div>
          </div>
          <div v-if="confirmed" class="confirmed-actions">
            <button class="button-primary" type="button" :disabled="exporting" @click="exportPdf">{{ exporting ? '正在提交导出…' : '导出 PDF' }}</button>
            <RouterLink class="button-secondary" :to="{ path: '/applications', query: { resumeVersionId: versionId, jdId: store.serverSnapshot.jdId } }">关联投递</RouterLink>
            <p>导出与投递均使用这个已确认版本。</p>
          </div>
          <p v-if="exportError" class="error-message editor-message" role="alert">{{ exportError }}</p>
          <p v-if="store.reviewable && !confirmed" class="toolbar-help">{{ store.busy ? '正在保存，编辑操作暂时锁定。' : store.dirty ? '先保存修改，再确认版本。' : store.reviewedCount < store.changes.length ? '逐项审阅并保存后，即可确认这个版本。' : '已完成审阅。确认后，此版本将不可修改。' }}</p>
        </section>
        <p v-if="store.notice" class="editor-message success-message" role="status">{{ store.notice }}</p>
        <div v-if="store.serverSnapshot.basedOnOldInput" class="editor-message old-input" role="note"><strong>这份草稿依据旧资料生成。</strong><p>{{ changedInputs }}已更新，此处仍保留生成时的原文与来源。需要使用新资料时，请重新准备材料。</p></div>
        <section v-if="store.conflict" class="conflict-panel" aria-label="版本冲突">
          <h2>{{ store.conflictLatest?.status === 'confirmed' ? '服务器上的版本已确认' : '这个版本已在其他页面更新' }}</h2>
          <p>{{ store.conflictLatest?.status === 'confirmed' ? '你的未保存内容仍保留在下方，可选中复制。已确认的版本无法覆盖或继续编辑。' : '你的修改仍保留。请核对服务器最新内容，再选择如何继续。' }}</p>
          <template v-if="store.conflictLatest">
            <details class="server-version" open>
              <summary>服务器最新版本 · 第 {{ store.conflictLatest.revision }} 版 · {{ store.conflictLatest.status === 'confirmed' ? '已确认' : '草稿' }}</summary>
              <ul class="server-decisions"><li v-for="change in serverChanges" :key="change.id"><span>{{ sectionLabel(change.section) }}</span><strong>{{ reviewLabels[change.status] }}</strong></li></ul>
              <ResumePreview :resume="serverPreview" title="服务器简历预览" />
            </details>
            <div class="conflict-actions"><button class="button-secondary" type="button" :disabled="store.busy" @click="store.useServerVersion()">使用服务器版本</button><button v-if="store.conflictLatest.status === 'draft' && reviewChanges(store.conflictLatest)" class="button-primary" type="button" :disabled="store.busy" @click="store.applyLocalChanges()">将我的修改应用到最新版本</button></div>
            <p v-if="store.conflictLatest.status === 'draft'" class="conflict-help">应用时只重放本页改过的决定，其他字段保留服务器的最新选择。应用后需要再次保存。</p>
          </template>
          <button v-else class="button-secondary" type="button" @click="store.loadConflict()">重新加载服务器版本</button>
        </section>
        <template v-if="store.reviewable">
          <div class="editor-columns">
            <div class="review-list" aria-label="逐项审阅">
              <div class="column-heading"><h2>{{ confirmed ? '审阅记录' : store.conflict ? '本页保留的修改' : '修改建议' }}</h2><p>{{ confirmed ? '每一次选择，都有迹可循。' : '接受、保留原文，或用你自己的话表达。' }}</p></div>
              <ChangeReview v-for="change in store.changes" :key="change.id" :change="change" :decision="store.localDecisions[change.id]!" :sources="store.serverSnapshot.sources || []" :disabled="!store.editable" :readonly="confirmed" @decision="store.decide" />
              <div v-if="!store.changes.length" class="card no-changes"><h3>无需修改建议</h3><p>核对右侧简历内容后，可以直接确认本版本。</p></div>
            </div>
            <aside class="preview-column"><div class="column-heading"><h2>{{ store.conflict ? '本页简历预览' : '预览你的简历' }}</h2><p>{{ confirmed ? '这是本次确认的完整正文。' : '根据当前选择即时更新，原始简历保持独立。' }}</p></div><ResumePreview :resume="store.preview" /></aside>
          </div>
          <p v-if="!confirmed" class="review-footnote">确认仅表示你已审阅这份简历，不会自动确认或修改长期事实。</p>
        </template>
        <section v-else class="card legacy-material">
          <h2>这份历史材料仅供查看</h2><p>它未包含可逐条审阅的建议。请返回材料准备，使用当前资料重新准备材料。</p>
          <dl><div v-for="entry in legacyEntries" :key="entry.key"><dt>{{ resumeLabels[entry.key] || entry.label }}</dt><dd v-if="entry.value">{{ entry.value }}</dd><dd v-for="child in entry.children" :key="child.label">{{ child.label }}：{{ child.value }}</dd><dd v-for="(group, index) in entry.groups" :key="index"><p v-if="group.value">{{ group.value }}</p><p v-for="child in group.children" :key="child.label">{{ child.label }}：{{ child.value }}</p></dd></div></dl>
        </section>
      </template>
    </template>
  </div>
</template>
<script setup lang="ts">
import { createUuid } from '../utils/uuid'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, RouterLink, useRoute, useRouter } from 'vue-router'
import { exportResumeVersion } from '../api/resumeVersions'
import { useResumeEditorStore } from '../stores/resumeEditor'
import { useAuthStore } from '../stores/auth'
import { decisionsFor, projectResume, resumeLabels, reviewChanges, reviewLabels, sectionLabel } from '../utils/resumeReview'
import { formatStructuredEntries } from '../utils/structuredDisplay'
import ChangeReview from '../components/resume/ChangeReview.vue'
import ResumePreview from '../components/resume/ResumePreview.vue'
const route = useRoute(), router = useRouter(), auth = useAuthStore(), store = useResumeEditorStore()
const versionId = computed(() => String(route.params.versionId || ''))
const exporting = ref(false), exportError = ref('')
let exportIntent: { versionId: string; requestId: string } | undefined
async function exportPdf() {
  if (!confirmed.value || exporting.value) return
  const id = versionId.value
  if (exportIntent?.versionId !== id) exportIntent = { versionId: id, requestId: createUuid() }
  exporting.value = true; exportError.value = ''
  try {
    const run = await exportResumeVersion(id, exportIntent.requestId)
    if (versionId.value !== id) return
    exportIntent = undefined
    await router.push(`/agent/tasks/${run.runId}`)
  } catch (cause) { if (versionId.value === id) exportError.value = cause instanceof Error ? cause.message : '暂时无法导出，请重试' }
  finally { exporting.value = false }
}
const confirmed = computed(() => store.serverSnapshot?.status === 'confirmed')
const serverChanges = computed(() => reviewChanges(store.conflictLatest) || [])
const serverPreview = computed(() => projectResume(store.conflictLatest, decisionsFor(serverChanges.value)))
const legacyEntries = computed(() => formatStructuredEntries(store.serverSnapshot?.structuredContent || {}))
const changedInputs = computed(() => (store.serverSnapshot?.changedInputs || []).map(key => ({ resume: '简历', jd: '岗位', facts: '已确认事实' })[key] || key).join('、') || '相关资料')
watch([versionId, () => auth.token], ([id, token]) => { if (token && id) void store.loadVersion(id); else store.clear() }, { immediate: true })
function allowLeave() { return !store.dirty || window.confirm('你有未保存的修改。离开后将丢弃这些修改，确定离开吗？') }
onBeforeRouteLeave(allowLeave)
onBeforeRouteUpdate((to, from) => to.params.versionId === from.params.versionId || allowLeave())
function beforeUnload(event: BeforeUnloadEvent) { if (store.dirty) { event.preventDefault(); event.returnValue = '' } }
onMounted(() => window.addEventListener('beforeunload', beforeUnload))
onBeforeUnmount(() => { window.removeEventListener('beforeunload', beforeUnload); store.clear() })
</script>
<style scoped>
.editor-page { gap: 20px; }
.back-link { width: fit-content; color: var(--color-text-secondary); text-decoration: none; font-size: 13px; line-height: 1.8; padding-block: 5px; }
.back-link:hover { color: var(--color-primary); text-decoration: underline; text-underline-offset: 4px; }
.editor-intro { border: 1px solid var(--color-primary-border); }
.editor-intro .section-head { margin-bottom: 20px; }
.editor-intro h2 { font-size: 22px; color: var(--color-primary); line-height: 1.5; }
.editor-intro .eyebrow { margin: 0 0 7px; color: var(--color-text-secondary); font-size: 12px; }
.version-stamp { border-radius: 8px; padding: 8px 12px; background: var(--color-primary-light); color: var(--color-primary); font-size: 13px; white-space: nowrap; }
.review-toolbar { display: flex; justify-content: space-between; flex-wrap: wrap; align-items: center; gap: 16px; border-top: 1px solid var(--color-border); padding-top: 20px; }
.review-progress { display: flex; flex-wrap: wrap; align-items: center; gap: 10px 16px; font-size: 13px; color: var(--color-text-secondary); }
.review-progress > span:first-child { color: var(--color-primary); font-weight: 600; }
.unsaved-state { color: var(--color-warning); }
.confirmed-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; margin-top: 20px; }
.confirmed-actions a { text-decoration: none; }
.confirmed-actions p { flex-basis: 100%; margin: 0; font-size: 12px; line-height: 1.7; color: var(--color-text-secondary); }
.save-actions,.conflict-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; }
.toolbar-help,.review-footnote { margin: 12px 0 0; font-size: 12px; line-height: 1.7; color: var(--color-text-secondary); }
.editor-message { padding: 16px 20px; border-radius: var(--radius-sm); font-size: 13px; line-height: 1.8; margin: 0; }
.editor-message p { margin: 0; } .editor-message button { margin-top: 12px; }
.error-message { background: #fff3f0; color: var(--color-danger); border: 1px solid #ebc9c0; }
.success-message { background: #edf3f6; border: 1px solid #ccdce5; color: var(--color-success); }
.old-input { background: var(--surface-panel-muted); border: 1px solid var(--color-primary-border); color: var(--color-warning); }
.old-input strong { display: block; margin-bottom: 4px; }
.editor-columns { display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr); align-items: start; gap: 24px; }
.review-list,.preview-column { display: grid; min-width: 0; gap: 16px; }
.column-heading { padding: 4px 0; }
.column-heading h2 { margin: 0; font-size: 15px; line-height: 1.6; }
.column-heading p { margin: 4px 0 0; color: var(--color-text-secondary); font-size: 12px; line-height: 1.7; }
.preview-column { position: sticky; top: 20px; }
.no-changes h3 { margin: 0 0 8px; font-size: 15px; } .no-changes p { margin: 0; font-size: 13px; line-height: 1.8; color: var(--color-text-secondary); }
.conflict-panel { display: grid; gap: 16px; border: 1px solid var(--color-primary-border); background: var(--color-bg-subtle); border-radius: var(--radius-sm); padding: 24px; min-width: 0; }
.conflict-panel h2 { margin: 0; font-size: 18px; line-height: 1.6; color: var(--color-primary); }
.conflict-panel > p { margin: 0; color: var(--color-text-secondary); font-size: 13px; line-height: 1.8; }
.server-version { min-width: 0; } .server-version summary { cursor: pointer; font-size: 13px; font-weight: 600; color: var(--color-primary); line-height: 1.8; }
.server-decisions { display: grid; gap: 8px; padding: 12px 0; margin: 8px 0; list-style: none; }
.server-decisions li { display: flex; flex-wrap: wrap; gap: 8px 16px; font-size: 13px; line-height: 1.6; }
.server-decisions strong { color: var(--color-success); font-weight: 500; }
.conflict-actions button { white-space: normal; line-height: 1.6; }
.conflict-panel .conflict-help { font-size: 12px; }
.legacy-material h2 { margin: 0 0 12px; font-size: 18px; } .legacy-material > p { font-size: 13px; color: var(--color-text-secondary); line-height: 1.8; }
.legacy-material dl { margin-top: 24px; display: grid; gap: 20px; } .legacy-material dt { font-weight: 600; font-size: 14px; } .legacy-material dd { margin: 8px 0 0; font-size: 14px; line-height: 1.8; white-space: pre-wrap; overflow-wrap: anywhere; }
@media (max-width: 1100px) { .editor-columns { grid-template-columns: 1fr; } .preview-column { position: static; } }
@media (max-width: 767px) { .editor-intro,.conflict-panel { padding: 20px; } .editor-intro h2 { font-size: 20px; } .review-toolbar { gap: 16px; } .save-actions { width: 100%; } .save-actions button { flex: 1; } .editor-columns { gap: 24px; } .editor-message { padding: 16px; } .conflict-actions { align-items: stretch; flex-direction: column; } }
</style>
