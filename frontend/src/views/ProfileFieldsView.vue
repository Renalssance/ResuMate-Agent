<template>
  <div class="profile-fields-page">
    <section class="profile-fields-toolbar">
      <label class="card form-field profile-resume-card">
        <span>选择简历</span>
        <select v-model="selectedResumeId" class="input" :disabled="isEditing || saving">
          <option value="">请选择简历</option>
          <option v-for="resume in parsedResumes" :key="resume.id" :value="resume.id">
            {{ resume.filename }}
          </option>
        </select>
      </label>

      <div class="card profile-coverage-card">
        <span>招聘字段已填写</span>
        <strong>{{ filledRequiredCount }} <small>/ {{ requiredFields.length }}</small></strong>
      </div>
    </section>

    <section v-if="store.listLoading && !parsedResumes.length" class="card loading-state" role="status">正在加载简历资料…</section>
    <section v-else-if="store.error && !selectedResume" class="card" role="alert">
      <div class="section-head"><h2>资料加载失败</h2><button class="button-secondary" type="button" :disabled="store.listLoading" @click="store.loadDocuments">重新加载</button></div>
      <p class="error-note">{{ store.error }}</p>
    </section>
    <section v-else-if="!selectedResume" class="card profile-empty-card">
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
            <button v-if="!isEditing" class="button-primary" type="button" @click="startEditing">
              <Pencil class="app-icon" aria-hidden="true" />
              <span>编辑</span>
            </button>
            <span v-else class="editing-hint">正在编辑，完成后在下方保存或取消。</span>
          </div>
        </div>

        <div v-if="message" :class="saveFailed ? 'error-note' : 'save-message'" role="status">{{ message }}</div>

        <fieldset class="profile-edit-body">
          <div class="field-grid profile-basic-grid">
            <div class="profile-field"><label><span>姓名</span><input v-model="draft.candidate_name" :readonly="!canEdit" /></label><CopyFieldButton :value="draft.candidate_name" label="姓名" /></div>
            <div class="profile-field span-two"><label><span>邮箱</span><input v-model="draft.contact.email" :readonly="!canEdit" /></label><CopyFieldButton :value="draft.contact.email" label="邮箱" /></div>
            <div class="profile-field"><label><span>手机</span><input v-model="draft.contact.phone" :readonly="!canEdit" /></label><CopyFieldButton :value="draft.contact.phone" label="手机" /></div>
            <div class="profile-field"><label><span>当前城市</span><input v-model="draft.contact.location" :readonly="!canEdit" /></label><CopyFieldButton :value="draft.contact.location" label="当前城市" /></div>
            <div class="profile-field"><label><span>微信</span><input v-model="draft.contact.wechat" :readonly="!canEdit" /></label><CopyFieldButton :value="draft.contact.wechat" label="微信" /></div>
            <div class="profile-field"><label><span>性别</span><input v-model="draft.application.gender" :readonly="!canEdit" /></label><CopyFieldButton :value="draft.application.gender" label="性别" /></div>
            <div class="profile-field"><label><span>出生日期</span><input v-model="draft.application.birth_date" :readonly="!canEdit" placeholder="1999.01.01" /></label><CopyFieldButton :value="draft.application.birth_date" label="出生日期" /></div>
            <div class="profile-field"><label><span>国籍</span><input v-model="draft.application.nationality" :readonly="!canEdit" /></label><CopyFieldButton :value="draft.application.nationality" label="国籍" /></div>
            <div class="profile-field"><label><span>政治面貌</span><input v-model="draft.application.political_status" :readonly="!canEdit" /></label><CopyFieldButton :value="draft.application.political_status" label="政治面貌" /></div>
            <div class="profile-field"><label><span>籍贯</span><input v-model="draft.application.native_place" :readonly="!canEdit" /></label><CopyFieldButton :value="draft.application.native_place" label="籍贯" /></div>
            <div class="profile-field"><label><span>户口所在地</span><input v-model="draft.application.hukou_location" :readonly="!canEdit" /></label><CopyFieldButton :value="draft.application.hukou_location" label="户口所在地" /></div>
            <div class="profile-field"><label><span>民族</span><input v-model="draft.application.ethnicity" :readonly="!canEdit" /></label><CopyFieldButton :value="draft.application.ethnicity" label="民族" /></div>
            <div class="profile-field"><label><span>内推码</span><input v-model="draft.application.referral_code" :readonly="!canEdit" /></label><CopyFieldButton :value="draft.application.referral_code" label="内推码" /></div>
            <div class="profile-field"><label><span>期望城市</span><input v-model="draft.application.expected_city" :readonly="!canEdit" /></label><CopyFieldButton :value="draft.application.expected_city" label="期望城市" /></div>
            <div class="profile-field"><label><span>期望职位</span><input v-model="draft.application.expected_position" :readonly="!canEdit" /></label><CopyFieldButton :value="draft.application.expected_position" label="期望职位" /></div>
            <div class="profile-field"><label><span>期望薪资</span><input v-model="draft.application.expected_salary" :readonly="!canEdit" /></label><CopyFieldButton :value="draft.application.expected_salary" label="期望薪资" /></div>
            <div class="profile-field"><label><span>最早到岗时间</span><input v-model="draft.application.earliest_start_date" :readonly="!canEdit" /></label><CopyFieldButton :value="draft.application.earliest_start_date" label="最早到岗时间" /></div>
            <div class="profile-field span-two"><label><span>现居地址</span><input v-model="draft.application.current_address" :readonly="!canEdit" /></label><CopyFieldButton :value="draft.application.current_address" label="现居地址" /></div>
            <div class="profile-field span-two"><label><span>个人主页 / 作品集</span><input v-model="draft.application.portfolio_url" :readonly="!canEdit" /></label><CopyFieldButton :value="draft.application.portfolio_url" label="个人主页 / 作品集" /></div>
            <div class="profile-field span-two"><label><span>GitHub / 代码仓库</span><input v-model="draft.application.github_url" :readonly="!canEdit" /></label><CopyFieldButton :value="draft.application.github_url" label="GitHub / 代码仓库" /></div>
            <div class="profile-field span-two"><label><span>LinkedIn / 领英</span><input v-model="draft.application.linkedin_url" :readonly="!canEdit" /></label><CopyFieldButton :value="draft.application.linkedin_url" label="LinkedIn / 领英" /></div>
            <div class="profile-field"><label><span>紧急联系人</span><input v-model="draft.application.emergency_contact_name" :readonly="!canEdit" /></label><CopyFieldButton :value="draft.application.emergency_contact_name" label="紧急联系人" /></div>
            <div class="profile-field"><label><span>紧急联系电话</span><input v-model="draft.application.emergency_contact_phone" :readonly="!canEdit" /></label><CopyFieldButton :value="draft.application.emergency_contact_phone" label="紧急联系电话" /></div>
            <div class="profile-field"><label><span>证件类型</span><input v-model="draft.application.id_document_type" :readonly="!canEdit" placeholder="如：中国 - 居民身份证" /></label><CopyFieldButton :value="draft.application.id_document_type" label="证件类型" /></div>
            <div class="profile-field span-two"><label><span>身份证号</span><input v-model="draft.application.id_number" :readonly="!canEdit" /></label><CopyFieldButton :value="draft.application.id_number" label="身份证号" /></div>
          </div>

          <details class="editor-section" open>
          <summary>教育经历</summary>
          <div v-for="(item, index) in draft.education" :key="index" class="repeat-card">
            <div class="repeat-head">
              <strong>教育 {{ index + 1 }}</strong>
              <button class="link-button danger-text" type="button" :disabled="!canEdit" @click="removeItem('education', index)">
                <Trash2 class="app-icon" aria-hidden="true" />
                <span>删除</span>
              </button>
            </div>
            <div class="field-grid profile-detail-grid">
              <div class="profile-field"><label><span>学校名称</span><input v-model="item.school" :readonly="!canEdit" /></label><CopyFieldButton :value="item.school" label="学校名称" /></div>
              <div class="profile-field"><label><span>学院</span><input v-model="item.college" :readonly="!canEdit" /></label><CopyFieldButton :value="item.college" label="学院" /></div>
              <div class="profile-field"><label><span>专业</span><input v-model="item.major" :readonly="!canEdit" /></label><CopyFieldButton :value="item.major" label="专业" /></div>
              <div class="profile-field"><label><span>学历/学位</span><input v-model="item.degree" :readonly="!canEdit" /></label><CopyFieldButton :value="item.degree" label="学历/学位" /></div>
              <div class="profile-field"><label><span>GPA</span><input v-model="item.gpa" :readonly="!canEdit" /></label><CopyFieldButton :value="item.gpa" label="GPA" /></div>
              <div class="profile-field"><label><span>成绩排名</span><input v-model="item.rank" :readonly="!canEdit" /></label><CopyFieldButton :value="item.rank" label="成绩排名" /></div>
              <div class="profile-field"><label><span>入学时间</span><input v-model="item.start_date" :readonly="!canEdit" placeholder="2024.09" /></label><CopyFieldButton :value="item.start_date" label="入学时间" /></div>
              <div class="profile-field"><label><span>毕业时间</span><input v-model="item.end_date" :readonly="!canEdit" placeholder="2027.06" /></label><CopyFieldButton :value="item.end_date" label="毕业时间" /></div>
              <div class="profile-field"><label><span>实验室</span><input v-model="item.lab" :readonly="!canEdit" /></label><CopyFieldButton :value="item.lab" label="实验室" /></div>
              <div class="profile-field"><label><span>领域方向</span><input v-model="item.research_direction" :readonly="!canEdit" /></label><CopyFieldButton :value="item.research_direction" label="领域方向" /></div>
              <div class="profile-field"><label><span>导师</span><input v-model="item.advisor" :readonly="!canEdit" /></label><CopyFieldButton :value="item.advisor" label="导师" /></div>
              <div class="profile-field span-two"><label><span>论文</span><input v-model="item.papers" :readonly="!canEdit" /></label><CopyFieldButton :value="item.papers" label="论文" /></div>
            </div>
          </div>
          <button class="button-secondary" type="button" :disabled="!canEdit" @click="addEducation">
            <Plus class="app-icon" aria-hidden="true" />
            <span>添加教育经历</span>
          </button>
          </details>

          <details class="editor-section" open>
          <summary>工作 / 实习经历</summary>
          <div v-for="(item, index) in draft.work_experience" :key="index" class="repeat-card">
            <div class="repeat-head">
              <strong>经历 {{ index + 1 }}</strong>
              <button class="link-button danger-text" type="button" :disabled="!canEdit" @click="removeItem('work_experience', index)">
                <Trash2 class="app-icon" aria-hidden="true" />
                <span>删除</span>
              </button>
            </div>
            <div class="field-grid profile-detail-grid">
              <div class="profile-field"><label><span>公司名称</span><input v-model="item.company" :readonly="!canEdit" /></label><CopyFieldButton :value="item.company" label="公司名称" /></div>
              <div class="profile-field"><label><span>职位名称</span><input v-model="item.title" :readonly="!canEdit" /></label><CopyFieldButton :value="item.title" label="职位名称" /></div>
              <div class="profile-field"><label><span>开始时间</span><input v-model="item.start_date" :readonly="!canEdit" /></label><CopyFieldButton :value="item.start_date" label="开始时间" /></div>
              <div class="profile-field"><label><span>结束时间</span><input v-model="item.end_date" :readonly="!canEdit" /></label><CopyFieldButton :value="item.end_date" label="结束时间" /></div>
              <div class="profile-field span-two"><label><span>描述</span><textarea v-model="item.description" :readonly="!canEdit"></textarea></label><CopyFieldButton :value="item.description" label="描述" /></div>
            </div>
          </div>
          <button class="button-secondary" type="button" :disabled="!canEdit" @click="addWork">
            <Plus class="app-icon" aria-hidden="true" />
            <span>添加工作/实习经历</span>
          </button>
          </details>

          <details class="editor-section" open>
          <summary>项目经历</summary>
          <div v-for="(item, index) in draft.projects" :key="index" class="repeat-card">
            <div class="repeat-head">
              <strong>项目 {{ index + 1 }}</strong>
              <button class="link-button danger-text" type="button" :disabled="!canEdit" @click="removeItem('projects', index)">
                <Trash2 class="app-icon" aria-hidden="true" />
                <span>删除</span>
              </button>
            </div>
            <div class="field-grid profile-detail-grid">
              <div class="profile-field"><label><span>项目名称</span><input v-model="item.name" :readonly="!canEdit" /></label><CopyFieldButton :value="item.name" label="项目名称" /></div>
              <div class="profile-field"><label><span>项目角色</span><input v-model="item.role" :readonly="!canEdit" /></label><CopyFieldButton :value="item.role" label="项目角色" /></div>
              <div class="profile-field"><label><span>开始时间</span><input v-model="item.start_date" :readonly="!canEdit" /></label><CopyFieldButton :value="item.start_date" label="开始时间" /></div>
              <div class="profile-field"><label><span>结束时间</span><input v-model="item.end_date" :readonly="!canEdit" /></label><CopyFieldButton :value="item.end_date" label="结束时间" /></div>
              <div class="profile-field span-two"><label><span>项目链接</span><input v-model="item.url" :readonly="!canEdit" /></label><CopyFieldButton :value="item.url" label="项目链接" /></div>
              <div class="profile-field span-two"><label><span>描述</span><textarea v-model="item.description" :readonly="!canEdit"></textarea></label><CopyFieldButton :value="item.description" label="描述" /></div>
            </div>
          </div>
          <button class="button-secondary" type="button" :disabled="!canEdit" @click="addProject">
            <Plus class="app-icon" aria-hidden="true" />
            <span>添加项目经历</span>
          </button>
          </details>

          <details class="editor-section" open>
          <summary>论文</summary>
          <div v-for="(item, index) in draft.papers" :key="index" class="repeat-card">
            <div class="repeat-head">
              <strong>论文 {{ index + 1 }}</strong>
              <button class="link-button danger-text" type="button" :disabled="!canEdit" @click="removeItem('papers', index)">
                <Trash2 class="app-icon" aria-hidden="true" />
                <span>删除</span>
              </button>
            </div>
            <div class="field-grid profile-detail-grid">
              <div class="profile-field"><label><span>论文名字</span><input v-model="item.name" :readonly="!canEdit" /></label><CopyFieldButton :value="item.name" label="论文名字" /></div>
              <div class="profile-field"><label><span>发表时间</span><input v-model="item.publication_date" :readonly="!canEdit" placeholder="2026.10" /></label><CopyFieldButton :value="item.publication_date" label="发表时间" /></div>
              <div class="profile-field"><label><span>发表单位</span><input v-model="item.publisher" :readonly="!canEdit" /></label><CopyFieldButton :value="item.publisher" label="发表单位" /></div>
              <div class="profile-field"><label><span>作者顺序</span><input v-model="item.author_order" :readonly="!canEdit" placeholder="如：第一作者、共同第一作者" /></label><CopyFieldButton :value="item.author_order" label="作者顺序" /></div>
              <div class="profile-field span-two"><label><span>论文介绍</span><textarea v-model="item.description" :readonly="!canEdit"></textarea></label><CopyFieldButton :value="item.description" label="论文介绍" /></div>
            </div>
          </div>
          <button class="button-secondary" type="button" :disabled="!canEdit" @click="addPaper">
            <Plus class="app-icon" aria-hidden="true" />
            <span>添加论文</span>
          </button>
          </details>

          <details class="editor-section" open>
          <summary>获奖经历</summary>
          <div v-for="(item, index) in draft.achievements" :key="index" class="repeat-card">
            <div class="repeat-head">
              <strong>获奖 {{ index + 1 }}</strong>
              <button class="link-button danger-text" type="button" :disabled="!canEdit" @click="removeItem('achievements', index)">
                <Trash2 class="app-icon" aria-hidden="true" />
                <span>删除</span>
              </button>
            </div>
            <div class="field-grid profile-detail-grid">
              <div class="profile-field"><label><span>获奖名称</span><input v-model="item.name" :readonly="!canEdit" /></label><CopyFieldButton :value="item.name" label="获奖名称" /></div>
              <div class="profile-field"><label><span>获奖时间</span><input v-model="item.date" :readonly="!canEdit" placeholder="2026.09" /></label><CopyFieldButton :value="item.date" label="获奖时间" /></div>
              <div class="profile-field"><label><span>奖励层级</span><input v-model="item.level" :readonly="!canEdit" placeholder="如：国家级、省级、校级" /></label><CopyFieldButton :value="item.level" label="奖励层级" /></div>
            </div>
          </div>
          <button class="button-secondary" type="button" :disabled="!canEdit" @click="addAward">
            <Plus class="app-icon" aria-hidden="true" />
            <span>添加获奖经历</span>
          </button>
          </details>

          <details class="editor-section">
          <summary>技能与其他</summary>
          <div class="field-grid profile-detail-grid">
            <div class="profile-field"><label><span>技能，每行一个</span><textarea v-model="skillsText" :readonly="!canEdit"></textarea></label><CopyFieldButton :value="skillsText" label="技能，每行一个" /></div>
            <div class="profile-field"><label><span>语言，每行一个</span><textarea v-model="languagesText" :readonly="!canEdit"></textarea></label><CopyFieldButton :value="languagesText" label="语言，每行一个" /></div>
            <div class="profile-field"><label><span>证书，每行一个</span><textarea v-model="certificationsText" :readonly="!canEdit"></textarea></label><CopyFieldButton :value="certificationsText" label="证书，每行一个" /></div>
            <div class="profile-field span-two"><label><span>自我介绍</span><textarea v-model="draft.self_summary" :readonly="!canEdit"></textarea></label><CopyFieldButton :value="draft.self_summary" label="自我介绍" /></div>
          </div>
          </details>
        </fieldset>
        <div v-if="isEditing" class="form-actions profile-form-actions">
          <button class="button-secondary" type="button" :disabled="saving" @click="cancelEditing">取消</button>
          <button class="button-primary" type="button" :disabled="saving" @click="saveDraft"><Save class="app-icon" aria-hidden="true" />{{ saving ? '保存中…' : '保存' }}</button>
        </div>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { Pencil, Plus, Save, Trash2 } from '@lucide/vue'
import { computed, onMounted, ref, watch } from 'vue'
import EmptyState from '../components/EmptyState.vue'
import CopyFieldButton from '../components/CopyFieldButton.vue'
import { emptyProfile, emptyEducation, emptyWork, emptyProject, emptyPaper, emptyAward, normalizeProfile } from '../utils/profileDraft'
import { useDocumentStore } from '../stores/document'
import { countFilledProfileFields, profileRequiredFields } from '../utils/profileFields'

type AnyRecord = Record<string, any>

const store = useDocumentStore()
const selectedResumeId = ref('')
const draft = ref<AnyRecord>(emptyProfile())
const isEditing = ref(false)
const saving = ref(false)
const canEdit = computed(() => isEditing.value && !saving.value)
const message = ref('')
const saveFailed = ref(false)

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

function resetDraft() {
  message.value = ''
  saveFailed.value = false
  draft.value = normalizeProfile(selectedResume.value?.parsedContent || {})
}

function cancelEditing() {
  resetDraft()
  isEditing.value = false
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

function addPaper() {
  draft.value.papers.push(emptyPaper())
}

function addAward() {
  draft.value.achievements.push(emptyAward())
}

function removeItem(section: 'education' | 'work_experience' | 'projects' | 'papers' | 'achievements', index: number) {
  draft.value[section].splice(index, 1)
}

async function saveDraft() {
  if (!selectedResume.value || saving.value) return
  const resumeId = selectedResume.value.id
  saveFailed.value = false
  saving.value = true
  message.value = ''
  try {
    await store.updateStructuredData(resumeId, draft.value)
    message.value = '已保存结构资料。'
    isEditing.value = false
  } catch (error) {
    saveFailed.value = true
    message.value = error instanceof Error ? error.message : String(error)
  } finally {
    saving.value = false
  }
}

function lines(value: string) {
  return value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean)
}

</script>
