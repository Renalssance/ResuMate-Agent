<template>
  <div class="extension-page page-stack">
    <section class="card extension-tool-card">
      <div class="section-head compact">
        <div>
          <h2>插件工具</h2>
          <p>收藏岗位、选择已确认的简历版本，在侧边栏核对后填表。</p>
        </div>
        <a class="button-primary download-button" :href="extensionDownload.href" :download="extensionDownload.filename">
          <FileText class="app-icon" aria-hidden="true" />
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
          <small>在插件设置中填写你的后端地址</small>
        </article>
        <article>
          <span>打开方式</span>
          <strong>浏览器侧边栏</strong>
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
            <h2>收藏与填表</h2>
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
import { FileText } from '@lucide/vue'
import { extensionDownload, extensionMeta, extensionWorkflow, installSteps, safetyNotes } from './extensionContent'
</script>
