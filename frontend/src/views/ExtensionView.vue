<template>
  <div class="extension-page page-stack">
    <section class="card extension-hero">
      <div>
        <span class="eyebrow">ResuMate Autofill</span>
        <h2>把已保存的简历资料填进招聘表单</h2>
        <p>
          插件会读取 ResuMate 中已解析的简历和结构字段，扫描当前招聘页面，先展示匹配结果，再由你选择要填充的项目。
        </p>
      </div>
      <a class="button-primary download-button" :href="extensionDownload.href" :download="extensionDownload.filename">
        {{ extensionDownload.label }}
      </a>
    </section>

    <section class="extension-grid">
      <div class="card">
        <div class="section-head compact">
          <div>
            <h2>安装插件</h2>
            <p>下载后按浏览器开发者模式加载本地扩展。</p>
          </div>
        </div>
        <ol class="step-list">
          <li v-for="step in installSteps" :key="step">{{ step }}</li>
        </ol>
      </div>

      <div class="card">
        <div class="section-head compact">
          <div>
            <h2>使用流程</h2>
            <p>从选择简历到填充字段，所有动作都需要你确认。</p>
          </div>
        </div>
        <ol class="step-list">
          <li v-for="step in usageSteps" :key="step">{{ step }}</li>
        </ol>
      </div>
    </section>

    <section class="card">
      <div class="section-head compact">
        <div>
          <h2>安全边界</h2>
          <p>插件只负责辅助填写，最终提交仍由你手动完成。</p>
        </div>
      </div>
      <div class="safety-list">
        <span v-for="note in safetyNotes" :key="note">{{ note }}</span>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { extensionDownload, installSteps, safetyNotes, usageSteps } from './extensionContent'
</script>

<style scoped>
.extension-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: var(--space-6);
  align-items: center;
}

.eyebrow {
  color: var(--color-primary);
  font-size: 13px;
  font-weight: 700;
}

.extension-hero h2 {
  margin: var(--space-2) 0;
  font-size: 28px;
  line-height: 1.2;
}

.extension-hero p {
  max-width: 760px;
  margin: 0;
  color: var(--color-text-secondary);
  line-height: 1.7;
}

.download-button {
  min-width: 128px;
  text-decoration: none;
}

.extension-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-4);
}

.step-list {
  display: grid;
  gap: var(--space-3);
  margin: 0;
  padding-left: 20px;
  color: var(--color-text-secondary);
  line-height: 1.7;
}

.step-list li::marker {
  color: var(--color-primary);
  font-weight: 700;
}

.safety-list {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
}

.safety-list span {
  padding: var(--space-2) var(--space-3);
  color: var(--color-text-secondary);
  background: var(--color-bg-subtle);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
}

@media (max-width: 900px) {
  .extension-hero,
  .extension-grid {
    grid-template-columns: 1fr;
  }

  .download-button {
    justify-self: start;
  }
}
</style>
