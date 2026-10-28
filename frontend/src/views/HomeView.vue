<template>
  <div class="rm-public rm-home">
    <a class="rm-skip" href="#main">跳至主要内容</a>
    <header class="rm-header rm-container">
      <BrandLogo />
      <nav class="rm-navigation" aria-label="首页导航">
        <a href="#features">产品能力</a>
        <a href="#milo">认识米洛</a>
      </nav>
      <div class="rm-header-actions">
        <RouterLink class="rm-login-link" to="/login">登录</RouterLink>
        <RouterLink class="rm-button rm-button-small" to="/register">注册 <ArrowUpRight :size="15" /></RouterLink>
      </div>
    </header>

    <main id="main">
      <section class="rm-hero rm-container" aria-labelledby="hero-title">
        <div class="rm-hero-copy">
          <span class="rm-eyebrow"><span class="rm-dot"></span> 有米洛陪伴，招聘多一点从容</span>
          <h1 id="hero-title">ResuMate：<br>你的招聘<span class="rm-underlined">好伙伴<svg viewBox="0 0 260 14" aria-hidden="true"><path d="M4 10 Q130 -3 256 7" /></svg></span></h1>
          <p class="rm-hero-description">和米洛一起，整理简历、发现匹配、准备面试。<br class="rm-desktop-break">让繁琐少一点，让每个闪光点被看见。</p>
          <div class="rm-hero-actions">
            <RouterLink class="rm-button" :to="auth.isAuthenticated ? '/documents' : '/register'">
              {{ auth.isAuthenticated ? '进入工作台' : '注册并开始使用' }} <ArrowRight :size="19" />
            </RouterLink>
            <RouterLink v-if="!auth.isAuthenticated" class="rm-button rm-button-outline" to="/login">已有账号，去登录</RouterLink>
          </div>
          <p class="rm-hero-note"><Check :size="15" /> 从一份简历开始，迈出下一步</p>
        </div>
        <div class="rm-mascot-stage">
          <div class="rm-mascot-blob" aria-hidden="true"></div>
          <span class="rm-speech">嗨，我是米洛！<span>你的招聘小搭档</span></span>
          <MiloMascot />
          <span class="rm-floating-note"><FileCheck2 :size="24" /><span>每一份经历<br><strong>都值得被发现</strong></span></span>
          <span class="rm-mascot-caption">MEET YOUR NEW MATE — MILO</span>
        </div>
      </section>

      <section id="features" class="rm-container rm-features" aria-label="产品能力">
        <a v-for="feature in features" :key="feature.title" :href="`#${feature.id}`" class="rm-feature">
          <component :is="feature.icon" :size="29" :stroke-width="1.6" aria-hidden="true" />
          <div><h2>{{ feature.title }}</h2><p>{{ feature.short }}</p></div>
          <ArrowUpRight :size="20" aria-hidden="true" />
        </a>
      </section>

      <section class="rm-workflow rm-container" aria-labelledby="workflow-title">
        <div class="rm-section-heading"><span class="rm-eyebrow">从资料到行动</span><h2 id="workflow-title">把时间，留给更重要的判断。</h2><p>米洛陪你理清信息，你来决定下一步。</p></div>
        <div class="rm-steps">
          <article v-for="(feature, index) in features" :id="feature.id" :key="feature.id" class="rm-step">
            <span class="rm-step-number">0{{ index + 1 }}</span>
            <component :is="feature.icon" :size="25" :stroke-width="1.5" aria-hidden="true" />
            <h3>{{ feature.heading }}</h3><p>{{ feature.description }}</p>
            <RouterLink :to="auth.isAuthenticated ? feature.path : '/register'">{{ feature.action }} <ArrowRight :size="16" /></RouterLink>
          </article>
        </div>
      </section>

      <section id="milo" class="rm-container rm-milo-section" aria-labelledby="milo-title">
        <div class="rm-milo-portrait"><img src="/images/milo-welcome.png" alt="米洛，奶油色与可可棕配色的猫咪伙伴" width="1300" height="1200" loading="lazy"></div>
        <div class="rm-milo-copy"><span class="rm-eyebrow">A LITTLE FRIEND, A LITTLE HELP</span><h2 id="milo-title">认识米洛，<br>认真陪伴的好伙伴。</h2><p>有点好奇，有点呆萌，最喜欢发现简历里的闪光点。米洛会在这里，陪你把零散的资料整理成清晰的线索。</p><div class="rm-personality"><span>耐心整理</span><span>发现闪光点</span><span>陪你向前</span></div></div>
      </section>

      <section class="rm-container rm-final-cta"><div><h2>下一段好故事，从这里开始。</h2><p>带上一份简历，剩下的和米洛一起梳理。</p></div><RouterLink class="rm-button" :to="auth.isAuthenticated ? '/documents' : '/register'">{{ auth.isAuthenticated ? '进入工作台' : '开始使用 ResuMate' }} <ArrowRight :size="18" /></RouterLink></section>
    </main>
    <footer class="rm-footer rm-container"><BrandLogo /><span>你的招聘好伙伴</span><a href="#main">回到顶部 ↑</a></footer>
  </div>
</template>

<script setup lang="ts">
import { ArrowRight, ArrowUpRight, Check, FileCheck2, Files, MessagesSquare, ScanSearch } from '@lucide/vue'
import MiloMascot from '../components/MiloMascot.vue'
import BrandLogo from '../components/BrandLogo.vue'
import { useAuthStore } from '../stores/auth'
const auth = useAuthStore()
const features = [
  { id: 'parse', icon: Files, title: '文档解析', short: '零散资料，清晰整理', heading: '先把经历，整理明白。', description: '上传简历与岗位描述，提取关键信息，保留原始资料，让每次查看都有据可循。', action: '整理我的文档', path: '/documents' },
  { id: 'match', icon: ScanSearch, title: '岗位匹配', short: '发现匹配，也看见依据', heading: '找到匹配，更读懂原因。', description: '结合岗位要求与简历经历，查看匹配分析和来源依据，让亮点与差距更清晰。', action: '开始岗位匹配', path: '/matching' },
  { id: 'prepare', icon: MessagesSquare, title: '面试准备', short: '问到重点，聊得深入', heading: '带着好问题，开启对话。', description: '基于岗位与候选人信息生成面试试题，把准备落到具体经历与能力上。', action: '准备面试试题', path: '/questions' },
]
</script>

