<template>
  <div class="profile-fields-page">
    <section class="card profile-fields-toolbar">
      <label class="resume-picker">
        <span>选择简历</span>
        <select v-model="selectedResumeId" class="input">
          <option value="">请选择简历</option>
          <option v-for="resume in parsedResumes" :key="resume.id" :value="resume.id">
            {{ resume.filename }}
          </option>
        </select>
      </label>

      <div class="coverage-card">
        <strong>{{ filledRequiredCount }} / {{ requiredFields.length }}</strong>
        <span>招聘字段已填写</span>
      </div>
    </section>

    <section v-if="!selectedResume" class="card profile-empty-card">
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
            <button v-if="!isEditing" class="button-primary" type="button" @click="startEditing">编辑</button>
            <template v-else>
              <button class="button-secondary" type="button" @click="resetDraft">还原</button>
              <button class="button-primary" type="button" :disabled="saving" @click="saveDraft">
                {{ saving ? '保存中...' : '保存' }}
              </button>
            </template>
          </div>
        </div>

        <div v-if="message" class="save-message">{{ message }}</div>

        <fieldset class="profile-edit-body" :disabled="!isEditing || saving">
          <div class="field-grid three">
            <label><span>姓名 <code>candidate_name</code></span><input v-model="draft.candidate_name" /></label>
            <label><span>邮箱 <code>contact.email</code></span><input v-model="draft.contact.email" /></label>
            <label><span>手机 <code>contact.phone</code></span><input v-model="draft.contact.phone" /></label>
            <label><span>当前城市 <code>contact.location</code></span><input v-model="draft.contact.location" /></label>
            <label><span>微信 <code>contact.wechat</code></span><input v-model="draft.contact.wechat" /></label>
            <label><span>性别 <code>application.gender</code></span><input v-model="draft.application.gender" /></label>
            <label><span>出生日期 <code>application.birth_date</code></span><input v-model="draft.application.birth_date" placeholder="1999.01.01" /></label>
            <label><span>国籍 <code>application.nationality</code></span><input v-model="draft.application.nationality" /></label>
            <label><span>政治面貌 <code>application.political_status</code></span><input v-model="draft.application.political_status" /></label>
            <label><span>籍贯 <code>application.native_place</code></span><input v-model="draft.application.native_place" /></label>
            <label><span>户口所在地 <code>application.hukou_location</code></span><input v-model="draft.application.hukou_location" /></label>
            <label><span>民族 <code>application.ethnicity</code></span><input v-model="draft.application.ethnicity" /></label>
            <label><span>内推码 <code>application.referral_code</code></span><input v-model="draft.application.referral_code" /></label>
            <label><span>期望城市 <code>application.expected_city</code></span><input v-model="draft.application.expected_city" /></label>
            <label><span>期望职位 <code>application.expected_position</code></span><input v-model="draft.application.expected_position" /></label>
            <label><span>期望薪资 <code>application.expected_salary</code></span><input v-model="draft.application.expected_salary" /></label>
            <label><span>最早到岗时间 <code>application.earliest_start_date</code></span><input v-model="draft.application.earliest_start_date" /></label>
            <label><span>现居地址 <code>application.current_address</code></span><input v-model="draft.application.current_address" /></label>
            <label><span>个人主页 / 作品集 <code>application.portfolio_url</code></span><input v-model="draft.application.portfolio_url" /></label>
            <label><span>GitHub / 代码仓库 <code>application.github_url</code></span><input v-model="draft.application.github_url" /></label>
            <label><span>LinkedIn / 领英 <code>application.linkedin_url</code></span><input v-model="draft.application.linkedin_url" /></label>
            <label><span>紧急联系人 <code>application.emergency_contact_name</code></span><input v-model="draft.application.emergency_contact_name" /></label>
            <label><span>紧急联系电话 <code>application.emergency_contact_phone</code></span><input v-model="draft.application.emergency_contact_phone" /></label>
            <label><span>证件类型 <code>application.id_document_type</code></span><input v-model="draft.application.id_document_type" placeholder="如：中国 - 居民身份证" /></label>
            <label><span>身份证号 <code>application.id_number</code></span><input v-model="draft.application.id_number" /></label>
          </div>

          <details class="editor-section" open>
          <summary>教育经历</summary>
          <div v-for="(item, index) in draft.education" :key="index" class="repeat-card">
            <div class="repeat-head">
              <strong>教育 {{ index + 1 }}</strong>
              <button class="link-button danger-text" type="button" @click="removeItem('education', index)">删除</button>
            </div>
            <div class="field-grid three">
              <label><span>学校名称 <code>education.0.school</code></span><input v-model="item.school" /></label>
              <label><span>学院 <code>education.0.college</code></span><input v-model="item.college" /></label>
              <label><span>专业 <code>education.0.major</code></span><input v-model="item.major" /></label>
              <label><span>学历/学位</span><input v-model="item.degree" /></label>
              <label><span>GPA <code>education.0.gpa</code></span><input v-model="item.gpa" /></label>
              <label><span>成绩排名 <code>education.0.rank</code></span><input v-model="item.rank" /></label>
              <label><span>入学时间</span><input v-model="item.start_date" placeholder="2024.09" /></label>
              <label><span>毕业时间</span><input v-model="item.end_date" placeholder="2027.06" /></label>
              <label><span>实验室 <code>education.0.lab</code></span><input v-model="item.lab" /></label>
              <label><span>领域方向 <code>education.0.research_direction</code></span><input v-model="item.research_direction" /></label>
              <label><span>导师 <code>education.0.advisor</code></span><input v-model="item.advisor" /></label>
              <label class="span-two"><span>论文 <code>education.0.papers</code></span><input v-model="item.papers" /></label>
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
              <label><span>项目名称 <code>projects.0.name</code></span><input v-model="item.name" /></label>
              <label><span>项目角色 <code>projects.0.role</code></span><input v-model="item.role" /></label>
              <label><span>开始时间</span><input v-model="item.start_date" /></label>
              <label><span>结束时间</span><input v-model="item.end_date" /></label>
              <label class="span-two"><span>项目链接 <code>projects.0.url</code></span><input v-model="item.url" /></label>
              <label class="span-two"><span>描述 <code>projects.0.description</code></span><textarea v-model="item.description"></textarea></label>
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
        </fieldset>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import EmptyState from '../components/EmptyState.vue'
import { useDocumentStore } from '../stores/document'
import { countFilledProfileFields, profileRequiredFields } from '../utils/profileFields'

type AnyRecord = Record<string, any>

const store = useDocumentStore()
const selectedResumeId = ref('')
const draft = ref<AnyRecord>(emptyProfile())
const isEditing = ref(false)
const saving = ref(false)
const message = ref('')

const parsedResumes = computed(() => store.parsedResumes)
const selectedResume = computed(() => parsedResumes.value.find((resume) => resume.id === selectedResumeId.value) || null)

const requiredFields = profileRequiredFields
const filledRequiredCount = computed(() => countFilledProfileFields(draft.value))

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

watch(selectedResume, () => {
  resetDraft()
  isEditing.value = false
}, { immediate: true })

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
  return { school: '', college: '', degree: '', major: '', gpa: '', rank: '', years: '', start_date: '', end_date: '', lab: '', research_direction: '', advisor: '', papers: '' }
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

function startEditing() {
  message.value = ''
  isEditing.value = true
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
    isEditing.value = false
  } catch (error) {
    message.value = error instanceof Error ? error.message : String(error)
  } finally {
    saving.value = false
  }
}

function lines(value: string) {
  return value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean)
}

</script>

<style scoped>
.profile-fields-page {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: var(--space-5);
  align-items: start;
}

.profile-fields-toolbar {
  display: grid;
  grid-template-columns: minmax(260px, 520px) auto;
  gap: var(--space-4);
  align-items: end;
}

.resume-picker {
  min-width: 0;
}

.profile-fields-toolbar .coverage-card {
  min-width: 190px;
  margin: 0;
  padding: 12px 16px;
}

.profile-empty-card {
  min-height: 280px;
  display: grid;
  align-items: center;
}

.editor-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: var(--space-2);
}

.profile-edit-body {
  min-width: 0;
  margin: 0;
  padding: 0;
  border: 0;
}

.profile-edit-body:disabled {
  opacity: 1;
}

.profile-edit-body:disabled input,
.profile-edit-body:disabled textarea {
  color: var(--color-text);
  background: rgba(244, 247, 245, 0.54);
  border-color: rgba(20, 35, 30, 0.08);
  cursor: default;
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

.editor-section {
  margin-top: var(--space-5);
}

.editor-section summary {
  margin-bottom: var(--space-4);
}

.repeat-card {
  margin-bottom: var(--space-4);
}

.save-message {
  margin-bottom: var(--space-4);
}

.field-grid label > span {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 5px;
}

.field-grid code {
  color: var(--color-analysis);
  background: rgba(61, 111, 159, 0.09);
  border-radius: 6px;
  font-size: 11px;
  font-weight: 650;
}

@media (min-width: 1281px) and (orientation: landscape) {
  .profile-fields-page {
    grid-template-rows: auto minmax(0, 1fr);
  }
}

@media (max-width: 1280px) {
  .field-grid.three {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 760px) {
  .profile-fields-page,
  .profile-fields-toolbar,
  .field-grid.three,
  .field-grid.two {
    grid-template-columns: 1fr;
  }

  .editor-actions {
    justify-content: stretch;
  }

  .editor-actions button {
    flex: 1 1 160px;
  }
}
</style>
