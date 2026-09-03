<template>
  <div class="extension-page page-stack">
    <section class="card extension-tool-card">
      <div class="section-head compact">
        <div>
          <h2>插件工具</h2>
          <p>下载、连接后端，并在招聘表单页打开侧边栏完成填充。</p>
        </div>
        <a class="button-primary download-button" :href="extensionDownload.href" :download="extensionDownload.filename">
          <span class="icon-glyph document" aria-hidden="true"></span>
          <span>{{ extensionDownload.label }}</span>
        </a>
      </div>

      <div class="extension-summary-grid">
        <article>
          <span>插件</span>
          <strong>{{ extensionMeta.name }}</strong>
          <small>{{ extensionMeta.manifest }} · v{{ extensionMeta.version }}</small>
        </article>
        <article>
          <span>后端地址</span>
          <strong>{{ extensionMeta.backend }}</strong>
          <small>{{ extensionMeta.profilesApi }}</small>
        </article>
        <article>
          <span>侧边栏入口</span>
          <strong>{{ extensionMeta.sidePanel }}</strong>
          <small>点击浏览器插件图标打开</small>
        </article>
      </div>
    </section>

    <section class="extension-grid">
      <div class="card">
        <div class="section-head compact">
          <div>
            <h2>安装检查</h2>
            <p>按顺序完成后即可在浏览器侧边栏使用。</p>
          </div>
        </div>
        <div class="extension-check-list">
          <span v-for="step in installSteps" :key="step">
            <i aria-hidden="true"></i>
            {{ step }}
          </span>
        </div>
      </div>

      <div class="card">
        <div class="section-head compact">
          <div>
            <h2>填表工作台</h2>
            <p>插件内的关键动作保持手动确认。</p>
          </div>
        </div>
        <div class="extension-workflow">
          <article v-for="step in extensionWorkflow" :key="step.title">
            <span>{{ step.label }}</span>
            <div>
              <strong>{{ step.title }}</strong>
              <small>{{ step.description }}</small>
            </div>
          </article>
        </div>
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
import { extensionDownload, extensionMeta, extensionWorkflow, installSteps, safetyNotes } from './extensionContent'
</script>
