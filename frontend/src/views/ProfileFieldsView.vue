<template>
  <div class="profile-fields-page">
    <section class="card profile-fields-rail">
      <div class="section-head compact">
        <div>
          <h2>选择简历</h2>
          <p>补充招聘表单常见字段，保存后插件会使用这些结构化资料。</p>
        </div>
      </div>

      <label>
        <span>已解析简历</span>
        <select v-model="selectedResumeId" class="input">
          <option value="">请选择简历</option>
          <option v-for="resume in parsedResumes" :key="resume.id" :value="resume.id">
            {{ resume.filename }}
          </option>
        </select>
      </label>

      <div class="coverage-card">
        <strong>{{ filledRequiredCount }} / {{ requiredFields.length }}</strong>
        <span>常见招聘字段已填写</span>
      </div>

      <div class="coverage-list">
        <div v-for="item in requiredFields" :key="item.path" :class="['coverage-row', { filled: hasValue(item.path) }]">
          <span>{{ item.label }}</span>
          <small>{{ hasValue(item.path) ? '已填写' : item.sensitive ? '建议保存，不默认自动填' : '待补充' }}</small>
        </div>
      </div>
    </section>

    <section v-if="!selectedResume" class="card">
      <EmptyState title="选择一份简历" description="上传并解析简历后，可以在这里检查、编辑和保存结构化字段。" />
    </section>

    <template v-else>
      <section class="card profile-fields-editor">
        <div class="section-head compact">
          <div>
            <h2>基础与求职资料</h2>
            <p>这些字段常出现在中国互联网招聘系统的基础信息、投递信息和补充资料里。</p>
          </div>
          <div class="editor-actions">
            <button class="button-secondary" type="button" @click="resetDraft">还原</button>
            <button class="button-primary" type="button" :disabled="saving" @click="saveDraft">
              {{ saving ? '保存中...' : '保存结构化资料' }}
            </button>
          </div>
        </div>

        <div v-if="message" class="save-message">{{ message }}</div>

        <div class="field-grid three">
          <label><span>姓名</span><input v-model="draft.candidate_name" /></label>
          <label><span>邮箱</span><input v-model="draft.contact.email" /></label>
          <label><span>手机</span><input v-model="draft.contact.phone" /></label>
          <label><span>当前城市</span><input v-model="draft.contact.location" /></label>
          <label><span>微信</span><input v-model="draft.contact.wechat" /></label>
          <label><span>性别</span><input v-model="draft.application.gender" /></label>
          <label><span>出生日期</span><input v-model="draft.application.birth_date" placeholder="1999.01.01" /></label>
          <label><span>国籍</span><input v-model="draft.application.nationality" /></label>
          <label><span>政治面貌</span><input v-model="draft.application.political_status" /></label>
          <label><span>籍贯</span><input v-model="draft.application.native_place" /></label>
          <label><span>户口所在地</span><input v-model="draft.application.hukou_location" /></label>
          <label><span>民族</span><input v-model="draft.application.ethnicity" /></label>
          <label><span>内推码</span><input v-model="draft.application.referral_code" /></label>
          <label><span>期望城市</span><input v-model="draft.application.expected_city" /></label>
          <label><span>期望职位</span><input v-model="draft.application.expected_position" /></label>
          <label><span>期望薪资</span><input v-model="draft.application.expected_salary" /></label>
          <label><span>最早到岗时间</span><input v-model="draft.application.earliest_start_date" /></label>
          <label><span>现居地址</span><input v-model="draft.application.current_address" /></label>
          <label><span>个人主页 / 作品集</span><input v-model="draft.application.portfolio_url" /></label>
          <label><span>GitHub / 代码仓库</span><input v-model="draft.application.github_url" /></label>
          <label><span>LinkedIn / 领英</span><input v-model="draft.application.linkedin_url" /></label>
          <label><span>紧急联系人</span><input v-model="draft.application.emergency_contact_name" /></label>
          <label><span>紧急联系电话</span><input v-model="draft.application.emergency_contact_phone" /></label>
          <label><span>证件类型</span><input v-model="draft.application.id_document_type" placeholder="如：中国 - 居民身份证" /></label>
        </div>

        <details class="editor-section" open>
          <summary>教育经历</summary>
          <div v-for="(item, index) in draft.education" :key="index" class="repeat-card">
            <div class="repeat-head">
              <strong>教育 {{ index + 1 }}</strong>
              <button class="link-button danger-text" type="button" @click="removeItem('education', index)">删除</button>
            </div>
            <div class="field-grid three">
              <label><span>学校名称</span><input v-model="item.school" /></label>
              <label><span>学院</span><input v-model="item.college" /></label>
              <label><span>专业</span><input v-model="item.major" /></label>
              <label><span>学历/学位</span><input v-model="item.degree" /></label>
              <label><span>入学时间</span><input v-model="item.start_date" placeholder="2024.09" /></label>
              <label><span>毕业时间</span><input v-model="item.end_date" placeholder="2027.06" /></label>
              <label><span>实验室</span><input v-model="item.lab" /></label>
              <label><span>领域方向</span><input v-model="item.research_direction" /></label>
              <label><span>导师</span><input v-model="item.advisor" /></label>
            </div>
          </div>
          <button class="button-secondary" type="button" @click="addEducation">添加教育经历</button>
        </details>

        <details class="editor-section" open>
          <summary>工作 / 实习经历</summary>
          <div v-for="(item, index) in draft.work_experience" :key="index" class="repeat-card">
            <div class="repeat-head">
              <strong>经历 {{ index + 1 }}</strong>
              <button class="link-button danger-text" type="button" @click="removeItem('work_experience', index)">删除</button>
            </div>
            <div class="field-grid two">
              <label><span>公司名称</span><input v-model="item.company" /></label>
              <label><span>职位名称</span><input v-model="item.title" /></label>
              <label><span>开始时间</span><input v-model="item.start_date" /></label>
              <label><span>结束时间</span><input v-model="item.end_date" /></label>
              <label class="span-two"><span>描述</span><textarea v-model="item.description"></textarea></label>
            </div>
          </div>
          <button class="button-secondary" type="button" @click="addWork">添加工作/实习经历</button>
        </details>

        <details class="editor-section" open>
          <summary>项目经历</summary>
          <div v-for="(item, index) in draft.projects" :key="index" class="repeat-card">
            <div class="repeat-head">
              <strong>项目 {{ index + 1 }}</strong>
              <button class="link-button danger-text" type="button" @click="removeItem('projects', index)">删除</button>
            </div>
            <div class="field-grid two">
              <label><span>项目名称</span><input v-model="item.name" /></label>
              <label><span>项目角色</span><input v-model="item.role" /></label>
              <label><span>开始时间</span><input v-model="item.start_date" /></label>
              <label><span>结束时间</span><input v-model="item.end_date" /></label>
              <label class="span-two"><span>项目链接</span><input v-model="item.url" /></label>
              <label class="span-two"><span>描述</span><textarea v-model="item.description"></textarea></label>
            </div>
          </div>
          <button class="button-secondary" type="button" @click="addProject">添加项目经历</button>
        </details>

        <details class="editor-section">
          <summary>技能与其他</summary>
          <div class="field-grid two">
            <label><span>技能，每行一个</span><textarea v-model="skillsText"></textarea></label>
            <label><span>语言，每行一个</span><textarea v-model="languagesText"></textarea></label>
            <label><span>证书，每行一个</span><textarea v-model="certificationsText"></textarea></label>
            <label><span>自我介绍</span><textarea v-model="draft.self_summary"></textarea></label>
          </div>
        </details>
      </section>

      <aside class="card profile-fields-aside">
        <h2>招聘字段对照</h2>
        <p>根据字节招聘和常见互联网校招/社招表单整理。敏感信息保存后仍由插件安全策略控制。</p>
        <div class="field-map">
          <div v-for="item in requiredFields" :key="item.path">
            <strong>{{ item.label }}</strong>
            <code>{{ item.path }}</code>
            <span>{{ valuePreview(item.path) || '未填写' }}</span>
          </div>
        </div>
      </aside>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import EmptyState from '../components/EmptyState.vue'
import { useDocumentStore } from '../stores/document'

type AnyRecord = Record<string, any>

const store = useDocumentStore()
const selectedResumeId = ref('')
const draft = ref<AnyRecord>(emptyProfile())
const saving = ref(false)
const message = ref('')

const parsedResumes = computed(() => store.parsedResumes)
const selectedResume = computed(() => parsedResumes.value.find((resume) => resume.id === selectedResumeId.value) || null)

const requiredFields = [
  { label: '姓名', path: 'candidate_name' },
  { label: '邮箱', path: 'contact.email' },
  { label: '手机', path: 'contact.phone' },
  { label: '当前城市', path: 'contact.location' },
  { label: '微信', path: 'contact.wechat' },
  { label: '性别', path: 'application.gender' },
  { label: '出生日期', path: 'application.birth_date' },
  { label: '国籍', path: 'application.nationality' },
  { label: '政治面貌', path: 'application.political_status' },
  { label: '籍贯', path: 'application.native_place' },
  { label: '户口所在地', path: 'application.hukou_location' },
  { label: '民族', path: 'application.ethnicity' },
  { label: '证件类型', path: 'application.id_document_type', sensitive: true },
  { label: '内推码', path: 'application.referral_code' },
  { label: '期望城市', path: 'application.expected_city' },
  { label: '期望职位', path: 'application.expected_position' },
  { label: '期望薪资', path: 'application.expected_salary' },
  { label: '最早到岗时间', path: 'application.earliest_start_date' },
  { label: '现居地址', path: 'application.current_address' },
  { label: '个人主页/作品集', path: 'application.portfolio_url' },
  { label: 'GitHub/代码仓库', path: 'application.github_url' },
  { label: 'LinkedIn/领英', path: 'application.linkedin_url' },
  { label: '紧急联系人', path: 'application.emergency_contact_name', sensitive: true },
  { label: '紧急联系电话', path: 'application.emergency_contact_phone', sensitive: true },
  { label: '学校名称', path: 'education.0.school' },
  { label: '学院', path: 'education.0.college' },
  { label: '专业', path: 'education.0.major' },
  { label: '实验室', path: 'education.0.lab' },
  { label: '领域方向', path: 'education.0.research_direction' },
  { label: '导师', path: 'education.0.advisor' },
  { label: '项目名称', path: 'projects.0.name' },
  { label: '项目角色', path: 'projects.0.role' },
  { label: '项目链接', path: 'projects.0.url' },
  { label: '项目描述', path: 'projects.0.description' },
]

const filledRequiredCount = computed(() => requiredFields.filter((item) => hasValue(item.path)).length)

const skillsText = computed({
  get: () => (draft.value.skills || []).map((item: any) => typeof item === 'string' ? item : item.name || '').filter(Boolean).join('\n'),
  set: (value: string) => {
    draft.value.skills = lines(value).map((name) => ({ name }))
  },
})
const languagesText = computed({
  get: () => (draft.value.languages || []).join('\n'),
  set: (value: string) => {
    draft.value.languages = lines(value)
  },
})
const certificationsText = computed({
  get: () => (draft.value.certifications || []).join('\n'),
  set: (value: string) => {
    draft.value.certifications = lines(value)
  },
})

onMounted(async () => {
  await store.loadDocuments()
  if (!selectedResumeId.value && parsedResumes.value[0]) selectedResumeId.value = parsedResumes.value[0].id
})

watch(selectedResume, () => resetDraft(), { immediate: true })

function emptyProfile(): AnyRecord {
  return {
    candidate_name: '',
    contact: {},
    application: {},
    education: [emptyEducation()],
    work_experience: [],
    projects: [emptyProject()],
    skills: [],
    languages: [],
    certifications: [],
    self_summary: '',
  }
}

function emptyEducation(): AnyRecord {
  return { school: '', college: '', degree: '', major: '', years: '', start_date: '', end_date: '', lab: '', research_direction: '', advisor: '' }
}

function emptyWork(): AnyRecord {
  return { company: '', title: '', duration: '', start_date: '', end_date: '', description: '' }
}

function emptyProject(): AnyRecord {
  return { name: '', role: '', duration: '', start_date: '', end_date: '', url: '', description: '' }
}

function normalizeProfile(input: Record<string, unknown> = {}): AnyRecord {
  const copy = JSON.parse(JSON.stringify(input || {}))
  const profile = { ...emptyProfile(), ...copy }
  profile.contact = { ...(copy.contact || {}) }
  profile.application = { ...(copy.application || {}) }
  profile.education = ensureArray(copy.education).map((item) => ({ ...emptyEducation(), ...item }))
  if (!profile.education.length) profile.education = [emptyEducation()]
  profile.work_experience = ensureArray(copy.work_experience || copy.experience).map((item) => ({ ...emptyWork(), ...item }))
  profile.projects = ensureArray(copy.projects).map((item) => ({ ...emptyProject(), ...item }))
  if (!profile.projects.length) profile.projects = [emptyProject()]
  profile.skills = ensureArray(copy.skills)
  profile.languages = ensureArray(copy.languages)
  profile.certifications = ensureArray(copy.certifications)
  return profile
}

function ensureArray(value: unknown): AnyRecord[] {
  return Array.isArray(value) ? value as AnyRecord[] : []
}

function resetDraft() {
  message.value = ''
  draft.value = normalizeProfile(selectedResume.value?.parsedContent || {})
}

function addEducation() {
  draft.value.education.push(emptyEducation())
}

function addWork() {
  draft.value.work_experience.push(emptyWork())
}

function addProject() {
  draft.value.projects.push(emptyProject())
}

function removeItem(section: 'education' | 'work_experience' | 'projects', index: number) {
  draft.value[section].splice(index, 1)
}

async function saveDraft() {
  if (!selectedResume.value) return
  saving.value = true
  message.value = ''
  try {
    await store.updateStructuredData(selectedResume.value.id, draft.value)
    message.value = '已保存，插件刷新简历后会使用最新字段。'
  } catch (error) {
    message.value = error instanceof Error ? error.message : String(error)
  } finally {
    saving.value = false
  }
}

function lines(value: string) {
  return value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean)
}

function valueAt(path: string) {
  return path.split('.').reduce<any>((target, part) => {
    if (target === undefined || target === null) return undefined
    return /^\d+$/.test(part) ? target[Number(part)] : target[part]
  }, draft.value)
}

function hasValue(path: string) {
  const value = valueAt(path)
  return Array.isArray(value) ? value.length > 0 : String(value || '').trim().length > 0
}

function valuePreview(path: string) {
  const value = valueAt(path)
  if (Array.isArray(value)) return value.join(', ')
  if (value && typeof value === 'object') return JSON.stringify(value)
  return String(value || '')
}
</script>

<style scoped>
.profile-fields-page {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr) 320px;
  gap: var(--space-4);
  align-items: start;
}

.profile-fields-rail,
.profile-fields-aside {
  position: sticky;
  top: 88px;
}

.section-head.compact {
  margin-bottom: var(--space-4);
}

.editor-actions {
  display: flex;
  gap: var(--space-3);
}

.field-grid {
  display: grid;
  gap: var(--space-3);
}

.field-grid.three {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.field-grid.two {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.span-two {
  grid-column: 1 / -1;
}

.coverage-card {
  margin-top: var(--space-4);
  padding: var(--space-4);
  background: var(--color-primary-light);
  border: 1px solid var(--color-primary-border);
  border-radius: var(--radius-md);
}

.coverage-card strong {
  display: block;
  color: var(--color-primary);
  font-size: 28px;
}

.coverage-card span,
.coverage-row small,
.profile-fields-aside p {
  color: var(--color-text-secondary);
  font-size: 13px;
}

.coverage-list,
.field-map {
  display: grid;
  gap: var(--space-2);
  margin-top: var(--space-4);
}

.coverage-row,
.field-map > div {
  display: grid;
  gap: 3px;
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-bg-subtle);
}

.coverage-row.filled {
  border-color: rgba(22, 163, 74, 0.35);
  background: #f0fdf4;
}

.coverage-row span,
.field-map strong {
  font-weight: 600;
}

.field-map code {
  overflow-wrap: anywhere;
  color: var(--color-primary);
  font-size: 12px;
}

.field-map span {
  overflow: hidden;
  color: var(--color-text-secondary);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.editor-section {
  margin-top: var(--space-5);
  border-top: 1px solid var(--color-border);
  padding-top: var(--space-4);
}

.editor-section summary {
  margin-bottom: var(--space-4);
  cursor: pointer;
  font-size: 16px;
  font-weight: 700;
}

.repeat-card {
  display: grid;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
  padding: var(--space-4);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-bg-subtle);
}

.repeat-head {
  display: flex;
  justify-content: space-between;
  gap: var(--space-3);
}

.save-message {
  margin-bottom: var(--space-4);
  padding: var(--space-3);
  color: var(--color-primary);
  background: var(--color-primary-light);
  border: 1px solid var(--color-primary-border);
  border-radius: var(--radius-sm);
}

@media (max-width: 1200px) {
  .profile-fields-page {
    grid-template-columns: 1fr;
  }

  .profile-fields-rail,
  .profile-fields-aside {
    position: static;
  }
}

@media (max-width: 760px) {
  .field-grid.three,
  .field-grid.two {
    grid-template-columns: 1fr;
  }

  .editor-actions {
    width: 100%;
    flex-wrap: wrap;
  }
}
</style>
