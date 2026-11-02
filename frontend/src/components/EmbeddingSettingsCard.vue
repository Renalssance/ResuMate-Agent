<template>
  <section class="model-card" aria-labelledby="embedding-heading">
    <form class="model-inline-form" @submit.prevent="save" @keydown.esc="cancelEdit">
      <header class="model-card-head">
        <h2 id="embedding-heading"><Layers class="app-icon" />Embedding</h2>
        <div class="model-actions">
          <button class="model-test" type="button" data-test-connection :disabled="loading || !settings || saving || testing" @click="testConnection"><Play class="app-icon" />{{ testing ? '测试中' : '测试' }}</button>
          <button v-if="editing" class="model-edit model-save" type="submit" :disabled="saving || testing"><Save class="app-icon" />{{ saving ? '保存中' : '保存' }}</button>
          <button v-else class="model-edit" type="button" data-edit-embedding :disabled="loading || !settings || testing" @click="editing = true; message = ''; error = ''"><Pencil class="app-icon" />编辑</button>
        </div>
      </header>
      <input id="embedding-model" v-model.trim="form.model" class="model-name" aria-label="Embedding 模型名称" :title="form.model" :readonly="!editing" :disabled="saving" required placeholder="配置模型名称" />
      <div class="model-fields model-credentials">
        <label class="model-field"><span>API Key</span><input id="embedding-key" v-model.trim="form.api_key" :title="form.api_key" :readonly="!editing" :disabled="saving || form.provider === 'local'" autocomplete="off" :placeholder="form.provider === 'local' ? '无需配置' : '未配置'" /></label>
        <label class="model-field"><span>Base URL</span><input id="embedding-url" v-model.trim="form.base_url" :title="form.base_url" :readonly="!editing" :disabled="saving || form.provider === 'local'" :required="form.provider !== 'local'" :placeholder="form.provider === 'local' ? '无需配置' : '未配置'" /></label>
      </div>
      <div class="model-fields model-provider">
        <label class="model-field"><span>服务类型</span>
          <select v-if="editing" id="embedding-provider" v-model="form.provider" :disabled="saving">
            <option value="openai">OpenAI</option><option value="qwen">Qwen</option><option value="local">本地模型</option>
          </select>
          <input v-else readonly :value="providerName" />
        </label>
      </div>
      <div class="model-feedback">
        <span v-if="error" role="alert">{{ error }}</span>
        <span v-else-if="message" role="status">{{ message }}</span>
        <span v-else-if="loading" role="status">加载中…</span>
        <button v-if="!loading && !settings" type="button" @click="load">重试</button>
      </div>
    </form>
  </section>
</template>
<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { Layers, Pencil, Play, Save } from '@lucide/vue'
import { fetchEmbeddingSettingsApi, saveEmbeddingSettingsApi, testEmbeddingSettingsApi } from '../api/settings'
import type { EmbeddingSettingsPayload, EmbeddingSettingsResponse } from '../types/settings'
const settings = ref<EmbeddingSettingsResponse | null>(null)
const editing = ref(false)
const loading = ref(true), saving = ref(false), testing = ref(false), error = ref(''), message = ref('')
const form = reactive<EmbeddingSettingsPayload>({ provider: 'openai', api_key: '', base_url: '', model: '' })
const providerName = computed(() => ({ openai: 'OpenAI', qwen: 'Qwen', local: '本地模型' })[form.provider])
function accept(value: EmbeddingSettingsResponse) {
  settings.value = value
  Object.assign(form, { provider: value.provider, base_url: value.base_url, model: value.model, api_key: value.api_key })
}
function cancelEdit() {
  if (settings.value) accept(settings.value)
  editing.value = false; error.value = ''; message.value = ''
}
async function load() {
  loading.value = true; error.value = ''
  try { accept(await fetchEmbeddingSettingsApi()) }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '加载失败' }
  finally { loading.value = false }
}
async function save() {
  if (saving.value) return
  saving.value = true; error.value = ''; message.value = ''
  try { accept(await saveEmbeddingSettingsApi({ ...form })); editing.value = false; message.value = '设置已保存' }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '保存失败' }
  finally { saving.value = false }
}
async function testConnection() {
  testing.value = true; error.value = ''; message.value = ''
  try { const result = await testEmbeddingSettingsApi(); message.value = `连接成功 · ${result.dimensions} 维` }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '连接测试失败' }
  finally { testing.value = false }
}
onMounted(load)
</script>
