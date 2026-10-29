<template>
 <section class="card workflow-card facts-panel" aria-label="确认事实">
  <div class="section-head"><div><h2>偏好与经历事实</h2><p>记录你的求职偏好与实际经历。只有明确确认的版本会用于材料准备。</p></div><button class="button-secondary" type="button" :disabled="loading" @click="loadFacts">重新加载事实</button></div>
  <p v-if="!auth.token" class="muted-note">登录后添加和查看你的事实。</p>
  <template v-else>
   <form class="fact-form" @submit.prevent="save">
    <div class="fact-fields"><label><span>事实类型</span><select v-model="kind" aria-label="事实类型" :disabled="!!editing || saving"><option value="preference">求职偏好</option><option value="experience">真实经历</option></select></label>
     <label v-if="!editing && experiences.length"><span>从简历选择经历</span><select v-model="selectedExperience" aria-label="从简历选择经历" :disabled="saving" @change="pickExperience"><option value="">手动填写</option><option v-for="item in experiences" :key="item.key" :value="item.key">{{ item.label }}</option></select></label>
    </div>
    <label><span>事实内容</span><textarea v-model="text" aria-label="事实内容" rows="3" required :disabled="saving" placeholder="如：希望在杭州工作；或填写一段你实际负责的项目经历。" /></label>
    <label class="check-label"><input v-model="confirmed" type="checkbox" data-confirm :disabled="saving" />我已核对，确认这条事实</label>
    <div class="fact-actions"><button class="button-primary" type="submit" :disabled="saving || !text.trim()">{{ saving ? '正在保存…' : editing ? '保存修改' : '保存事实' }}</button><button v-if="editing" class="button-secondary" type="button" :disabled="saving" @click="resetForm">取消编辑</button><span class="muted-note">{{ editing ? '修改会保留旧版本，并重新确认。' : kind === 'preference' ? '求职偏好适用于所有简历。' : resumeId ? '经历关联当前简历。' : '选择简历后可关联经历来源。' }}</span></div>
   </form>
   <p v-if="error" class="error-note" role="alert">{{ error }}</p><p v-if="notice" class="save-message" role="status">{{ notice }}</p>
   <div class="facts-list-head"><label class="check-label"><input v-model="includeDeleted" type="checkbox" />显示已删除事实</label><span>{{ items.length }} 条事实</span></div>
   <p v-if="loading" role="status">正在读取事实…</p><p v-else-if="!items.length && !error" class="muted-note">还没有事实。填写一条偏好，或从简历选择一段经历开始核对。</p>
   <ul class="fact-list"><li v-for="fact in items" :key="fact.id" class="fact-item"><div class="fact-meta"><strong>{{ fact.kind === 'preference' ? '求职偏好' : '真实经历' }}</strong><span>{{ fact.deletedAt ? '已删除' : fact.confirmedAt ? '已确认' : '未确认' }}</span><span>第 {{ fact.revision }} 版</span><span>{{ fact.sourceDocumentId ? '来源：当前简历' : '适用于所有简历' }}</span></div><p class="fact-text">{{ fact.content.text }}</p><div class="fact-actions"><button v-if="!fact.deletedAt" class="button-secondary" type="button" :disabled="saving" @click="edit(fact)">编辑事实</button><button v-if="!fact.deletedAt" class="button-secondary danger-text" type="button" :disabled="saving" @click="remove(fact)">删除事实</button><button class="button-secondary" type="button" @click="showHistory(fact)">查看历史</button></div>
    <div v-if="historyKey === fact.factKey" class="fact-history" aria-label="事实历史"><h3>版本历史</h3><p v-if="historyLoading">正在读取历史…</p><p v-if="historyError" class="error-note" role="alert">{{ historyError }}</p><ol><li v-for="version in history" :key="version.id"><strong>第 {{ version.revision }} 版 · {{ version.deletedAt ? '已删除' : version.confirmedAt ? '已确认' : '未确认' }}</strong><p class="fact-text">{{ version.content.text }}</p></li></ol></div>
   </li></ul>
  </template>
 </section>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useAuthStore } from '../stores/auth'
import { createProfileFact, deleteProfileFact, fetchFactHistory, fetchProfileFacts, updateProfileFact, type ProfileFact } from '../api/profileFacts'
const props = defineProps<{ resumeId?: string; parsedContent?: Record<string, unknown> }>()
const auth = useAuthStore(), items = ref<ProfileFact[]>([]), loading = ref(false), saving = ref(false), error = ref(''), notice = ref(''), includeDeleted = ref(false)
const kind = ref<ProfileFact['kind']>('preference'), text = ref(''), confirmed = ref(false), editing = ref<ProfileFact | null>(null), selectedExperience = ref('')
const historyKey = ref(''), history = ref<ProfileFact[]>([]), historyLoading = ref(false), historyError = ref('')
const sourceId = computed(() => props.resumeId ? Number(props.resumeId.split(':').pop()) : undefined)
let context = 0, request = 0, historyRequest = 0
const experiences = computed(() => ['work_experience', 'projects'].flatMap(section => {
 const values = props.parsedContent?.[section]; if (!Array.isArray(values)) return []
 return values.flatMap((value, index) => { if (!value || typeof value !== 'object') return []; const entry = value as Record<string, unknown>; const parts = [entry.company || entry.name, entry.title || entry.role, entry.start_date, entry.end_date, entry.description].filter(Boolean).map(String); return parts.length ? [{ key: `${section}:${index}`, label: parts.slice(0, 2).join(' · '), text: parts.join('\n'), section, index }] : [] })
}))
function resetForm() { editing.value = null; kind.value = 'preference'; text.value = ''; confirmed.value = false; selectedExperience.value = '' }
function pickExperience() { const entry = experiences.value.find(item => item.key === selectedExperience.value); if (entry) { kind.value = 'experience'; text.value = entry.text; confirmed.value = false } }
async function loadFacts() { const mine = ++request, scope = context; error.value = ''; loading.value = true; try { const result = await fetchProfileFacts(sourceId.value, includeDeleted.value); if (mine === request && scope === context) items.value = result.items } catch (e) { if (mine === request && scope === context) error.value = message(e) } finally { if (mine === request && scope === context) loading.value = false } }
function edit(fact: ProfileFact) { editing.value = fact; kind.value = fact.kind; text.value = fact.content.text; confirmed.value = false; selectedExperience.value = ''; error.value = ''; notice.value = '' }
function message(e: unknown) { return (e as { status?: number }).status === 409 ? '这条事实已在其他页面更新。你的输入已保留；重新加载事实后，核对最新版本再编辑。' : e instanceof Error ? e.message : '操作失败，请重试。' }
async function save() {
 if (saving.value || !text.value.trim()) return; error.value = ''; notice.value = ''; 
 const scope = context, isConfirmed = confirmed.value, current = editing.value, entry = experiences.value.find(item => item.key === selectedExperience.value)
 const content = { ...(current?.content || {}), text: text.value.trim(), ...(entry ? { sourceSection: entry.section, sourceIndex: entry.index } : {}) }
 saving.value = true
 try { if (current) await updateProfileFact(current.id, { expectedRevision: current.revision, content, confirmed: isConfirmed }); else await createProfileFact({ kind: kind.value, content, confirmed: isConfirmed, ...(kind.value === 'experience' && sourceId.value ? { sourceDocumentId: sourceId.value } : {}) }); if (scope !== context) return; resetForm(); notice.value = isConfirmed ? '事实已保存并确认。' : '事实已保存，尚未确认。'; historyKey.value = ''; await loadFacts() } catch (e) { if (scope === context) error.value = message(e) } finally { if (scope === context) saving.value = false }
}
async function remove(fact: ProfileFact) { if (saving.value) return; const scope = context; saving.value = true; error.value = ''; notice.value = ''; try { await deleteProfileFact(fact.id, fact.revision); if (scope !== context) return; if (editing.value?.factKey === fact.factKey) resetForm(); historyKey.value = ''; notice.value = '事实已删除，历史版本仍可查看。'; await loadFacts() } catch (e) { if (scope === context) error.value = message(e) } finally { if (scope === context) saving.value = false } }
async function showHistory(fact: ProfileFact) { const scope = context, mine = ++historyRequest; historyKey.value = fact.factKey; history.value = []; historyError.value = ''; historyLoading.value = true; try { const result = await fetchFactHistory(fact.id); if (scope === context && mine === historyRequest) history.value = result.items } catch (e) { if (scope === context && mine === historyRequest) historyError.value = message(e) } finally { if (scope === context && mine === historyRequest) historyLoading.value = false } }
watch([() => props.resumeId, () => auth.token], () => { context++; request++; historyRequest++; items.value = []; resetForm(); historyKey.value = ''; history.value = []; error.value = ''; notice.value = ''; saving.value = false; loading.value = false; if (auth.token) void loadFacts() }, { immediate: true })
watch(includeDeleted, () => { historyKey.value = ''; if (auth.token) void loadFacts() })
onBeforeUnmount(() => { context++; request++; historyRequest++ })
</script>
<style scoped>
.facts-panel { overflow-wrap: anywhere; } .fact-form,.fact-form label { display: grid; gap: 8px; } .fact-form { gap: 16px; padding-bottom: 24px; border-bottom: 1px solid var(--color-border); } .fact-fields { display: grid; grid-template-columns: minmax(150px,.5fr) minmax(0,1fr); gap: 20px; } .fact-form textarea { width: 100%; resize: vertical; min-height: 110px; } .fact-form select { width: 100%; min-width: 0; } .fact-form .check-label,.check-label { display: flex; gap: 9px; align-items: center; line-height: 1.6; } .check-label input { width: 17px; height: 17px; flex: 0 0 17px; accent-color: var(--color-primary); } .fact-actions { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; } .facts-list-head,.fact-meta { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; } .facts-list-head { justify-content: space-between; margin: 22px 0; color: var(--color-text-secondary); font-size: 14px; } .fact-list { list-style: none; padding: 0; margin: 0; display: grid; gap: 16px; } .fact-item { border: 1px solid var(--color-border); border-radius: var(--radius-sm); padding: 20px; } .fact-meta span,.muted-note { color: var(--color-text-secondary); font-size: 14px; line-height: 1.7; } .fact-text { white-space: pre-wrap; line-height: 1.8; margin: 12px 0 18px; } .fact-history { margin-top: 20px; padding: 18px; background: var(--surface-panel-muted); border-radius: var(--radius-sm); } .fact-history ol { padding-left: 20px; } .save-message { color: var(--color-success); } @media(max-width:700px) { .fact-fields { grid-template-columns: 1fr; } .section-head { flex-wrap: wrap; gap: 12px; } .fact-item { padding: 16px; } }
</style>
