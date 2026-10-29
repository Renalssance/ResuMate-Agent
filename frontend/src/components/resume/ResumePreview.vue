<template>
  <article class="resume-preview" :aria-label="title || '简历预览'">
    <div class="preview-caption"><span>{{ title || '简历预览' }}</span><span>当前表述</span></div>
    <header v-if="resume.candidate_name || contact.length" class="resume-person">
      <h2 v-if="resume.candidate_name">{{ resume.candidate_name }}</h2>
      <p v-if="contact.length">{{ contact.join(' · ') }}</p>
    </header>
    <section v-for="section in sections" :key="section.key" class="resume-section">
      <h3>{{ section.label }}</h3>
      <p v-if="section.text" class="resume-text">{{ section.text }}</p>
      <div v-for="(entry, index) in section.items" :key="index" class="resume-entry">
        <h4 v-if="entry.heading">{{ entry.heading }}</h4>
        <p v-if="entry.meta" class="entry-meta">{{ entry.meta }}</p>
        <p v-for="(line, lineIndex) in entry.lines" :key="lineIndex" class="resume-text">{{ line }}</p>
      </div>
    </section>
    <p v-if="!sections.length && !resume.candidate_name" class="empty-preview">暂无可预览的简历正文。</p>
  </article>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import { isRecord } from '../../utils/resumeReview'
const props = defineProps<{ resume: Record<string, unknown>; title?: string }>()
const text = (value: unknown): string => typeof value === 'string' || typeof value === 'number' ? String(value).trim() : ''
const textList = (value: unknown): string[] => Array.isArray(value) ? value.map(text).filter(Boolean) : text(value) ? [text(value)] : []
const join = (...values: unknown[]) => values.map(text).filter(Boolean).join(' · ')
const contact = computed(() => isRecord(props.resume.contact) ? Object.values(props.resume.contact).map(text).filter(Boolean) : [])
type Entry = { heading: string; meta: string; lines: string[] }
function entries(value: unknown, type: string): Entry[] {
  if (!Array.isArray(value)) return []
  return value.map(item => {
    if (!isRecord(item)) return { heading: '', meta: '', lines: textList(item) }
    if (type === 'education') return { heading: join(item.school, item.degree, item.major), meta: text(item.years) || join(item.start_date, item.end_date), lines: [join(item.college, item.lab, item.research_direction), ...textList(item.courses).map(line => `课程：${line}`), ...textList(item.papers), ...textList(item.achievements), item.gpa ? `GPA：${text(item.gpa)}` : '', item.rank ? `排名：${text(item.rank)}` : '', item.advisor ? `导师：${text(item.advisor)}` : ''].filter(Boolean) }
    if (type === 'work_experience' || type === 'projects') return { heading: type === 'projects' ? join(item.name, item.role) : join(item.company, item.title || item.role), meta: text(item.duration) || text(item.period) || join(item.start_date, item.end_date), lines: [text(item.description), ...(Array.isArray(item.bullets) ? item.bullets.map(bullet => isRecord(bullet) ? text(bullet.raw_text) : text(bullet)).filter(line => line && line !== text(item.description)) : []), ...textList(item.technologies).length ? [`技术：${textList(item.technologies).join('、')}`] : []].filter(Boolean) }
    return { heading: '', meta: '', lines: [join(item.name, item.proficiency_claim, item.level)].filter(Boolean) }
  }).filter(item => item.heading || item.meta || item.lines.length)
}
const sections = computed(() => {
  const resume = props.resume
  const definitions = [ ['self_summary', '个人简介'], ['education', '教育经历'], ['work_experience', '工作经历'], ['projects', '项目经历'], ['skills', '技能'], ['achievements', '成果与荣誉'], ['certifications', '证书'], ['languages', '语言'] ]
  return definitions.map(([key, label]) => ({ key: key!, label, text: key === 'self_summary' ? text(resume.self_summary ?? resume.summary) : ['certifications', 'languages'].includes(key!) ? textList(resume[key!]).join('、') : '', items: ['self_summary', 'certifications', 'languages'].includes(key!) ? [] : entries(resume[key!], key!) })).filter(section => section.text || section.items.length)
})
</script>
<style scoped>
.resume-preview { padding: 28px; border: 1px solid var(--color-primary-border); border-radius: var(--radius-sm); background: var(--surface-panel); min-width: 0; overflow-wrap: anywhere; }
.preview-caption { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; padding-bottom: 20px; border-bottom: 1px solid var(--color-border); color: var(--color-text-secondary); font-size: 12px; }
.preview-caption span:first-child { color: var(--color-primary); font-weight: 600; }
.resume-person { padding-top: 24px; }
.resume-person h2 { margin: 0 0 8px; color: var(--color-primary); font-size: 25px; line-height: 1.5; letter-spacing: 1px; }
.resume-person p { margin: 0; font-size: 12px; line-height: 1.8; color: var(--color-text-secondary); }
.resume-section { margin-top: 24px; }
.resume-section h3 { margin: 0 0 12px; padding-bottom: 7px; border-bottom: 1px solid var(--color-border); font-size: 13px; color: var(--color-primary); line-height: 1.6; letter-spacing: .5px; }
.resume-entry + .resume-entry { margin-top: 18px; }
.resume-entry h4 { margin: 0 0 4px; font-size: 14px; line-height: 1.7; }
.entry-meta { margin: 0 0 6px; color: var(--color-text-secondary); font-size: 12px; line-height: 1.7; }
.resume-text { margin: 5px 0 0; font-size: 13px; line-height: 1.9; white-space: pre-wrap; }
.empty-preview { color: var(--color-text-secondary); font-size: 13px; line-height: 1.8; padding-top: 20px; }
@media (max-width: 767px) { .resume-preview { padding: 20px; } }
</style>
