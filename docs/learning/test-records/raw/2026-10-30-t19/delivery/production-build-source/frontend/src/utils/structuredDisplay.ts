export interface StructuredChild {
  label: string
  value: string
}

export interface StructuredGroup {
  title: string
  value: string
  children: StructuredChild[]
}

export interface StructuredEntry {
  key: string
  label: string
  value: string
  children: StructuredChild[]
  groups: StructuredGroup[]
}

const labelMap: Record<string, string> = {
  candidate_name: '姓名',
  contact: '联系方式',
  application: '求职信息',
  title: '岗位名称',
  responsibilities: '岗位职责',
  requirements: '必备要求',
  bonus: '加分项',
  skills: '技能关键词',
  weights: '评价标准与权重',
  name: '基本信息',
  education: '教育经历',
  work: '工作经历',
  projects: '项目经历',
  achievements: '成果',
  ambiguities: '模糊点',
  phone: '手机',
  mobile: '手机',
  email: '邮箱',
  mailbox: '邮箱',
  location: '所在地',
  school: '学校',
  college: '学院',
  degree: '学历',
  major: '专业',
  years: '时间',
  start_date: '开始时间',
  end_date: '结束时间',
  courses: '课程',
}

export function formatStructuredEntries(content: Record<string, unknown>) {
  return Object.entries(content).map(([key, value]) => formatEntry(key, value))
}

function formatEntry(key: string, value: unknown): StructuredEntry {
  return {
    key,
    label: labelFor(key),
    value: isPlainRecord(value) || Array.isArray(value) ? '' : textFor(value),
    children: isPlainRecord(value) ? childrenFor(value) : [],
    groups: Array.isArray(value) ? groupsFor(value, labelFor(key)) : [],
  }
}

function groupsFor(value: unknown[], label: string) {
  return value.map((item, index) => ({
    title: value.length > 1 ? `${label} ${index + 1}` : '',
    value: isPlainRecord(item) ? '' : textFor(item),
    children: isPlainRecord(item) ? childrenFor(item) : [],
  }))
}

function childrenFor(value: Record<string, unknown>) {
  return Object.entries(value).map(([key, child]) => ({
    label: labelFor(key),
    value: textFor(child),
  }))
}

function textFor(value: unknown): string {
  if (typeof value === 'string') return value || '暂无'
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (Array.isArray(value)) return value.map(textFor).filter((item) => item !== '暂无').join('、') || '暂无'
  if (isPlainRecord(value)) return childrenFor(value).map((item) => `${item.label}: ${item.value}`).join('；') || '暂无'
  return '暂无'
}

function labelFor(key: string) {
  return labelMap[key] || key.replace(/_/g, ' ')
}

function isPlainRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && !Array.isArray(value) && typeof value === 'object'
}
