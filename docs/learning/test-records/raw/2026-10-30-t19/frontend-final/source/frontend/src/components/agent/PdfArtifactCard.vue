<template>
  <article class="pdf-artifact-card" aria-label="已导出的 PDF">
    <div class="section-head"><div><h3>你的简历 PDF 已准备好</h3><p>已确认版本 · 第 {{ artifact.revision }} 版</p></div><span class="pdf-badge">PDF</span></div>
    <p class="pdf-filename">{{ artifact.filename }}</p>
    <p class="muted-note">使用确认时的简历正文生成，可保存并用于投递。</p>
    <div class="pdf-actions">
      <button class="button-primary" type="button" :disabled="downloading" @click="download">{{ downloading ? '正在下载…' : '下载 PDF' }}</button>
      <RouterLink class="button-secondary" :to="`/resume-versions/${artifact.resumeVersionId}`">查看确认版本</RouterLink>
    </div>
    <p v-if="error" class="error-note" role="alert">{{ error }}</p>
    <p v-if="downloaded" class="muted-note" role="status">PDF 已下载，可在浏览器下载记录中查看。</p>
  </article>
</template>
<script setup lang="ts">
import { ref } from 'vue'
import { RouterLink } from 'vue-router'
import { AgentRunError, downloadResumePdf, type ResumePdfArtifact } from '../../api/agentRuns'
const props = defineProps<{ artifact: ResumePdfArtifact }>()
const downloading = ref(false), downloaded = ref(false), error = ref('')
async function download() {
  if (downloading.value) return
  downloading.value = true; error.value = ''; downloaded.value = false
  try {
    const blob = await downloadResumePdf(props.artifact.runId)
    const url = URL.createObjectURL(blob), link = document.createElement('a')
    link.href = url; link.download = props.artifact.filename
    document.body.appendChild(link); link.click(); link.remove(); URL.revokeObjectURL(url)
    downloaded.value = true
  } catch (cause) {
    error.value = cause instanceof AgentRunError && cause.code === 'artifact_missing' ? 'PDF 文件暂时不可用，请打开确认版本重新导出。' : cause instanceof Error ? cause.message : '下载失败，请重试'
  } finally { downloading.value = false }
}
</script>
<style scoped>
.pdf-artifact-card { display: grid; gap: 16px; padding: 24px; border: 1px solid var(--color-primary-border); border-radius: var(--radius-sm); background: var(--surface-panel); min-width: 0; overflow-wrap: anywhere; }
.section-head { margin: 0; } h3 { margin: 0; font-size: 18px; line-height: 1.6; } p { margin: 0; font-size: 13px; line-height: 1.8; }
.section-head p,.muted-note { color: var(--color-text-secondary); } .section-head p { margin-top: 6px; }
.pdf-badge { padding: 10px 12px; background: var(--color-primary-light); color: var(--color-primary); border-radius: 8px; font-size: 12px; letter-spacing: 1px; }
.pdf-filename { font-weight: 600; } .pdf-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; } .pdf-actions a { text-decoration: none; }
@media (max-width: 767px) { .pdf-artifact-card { padding: 20px; } .pdf-actions { align-items: stretch; } .pdf-actions > * { flex: 1; text-align: center; } }
</style>
