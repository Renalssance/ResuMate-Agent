export interface ProfileRequiredField {
  label: string
  path: string
  sensitive?: boolean
}

export const profileRequiredFields: ProfileRequiredField[] = [
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
  { label: '身份证号', path: 'application.id_number', sensitive: true },
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
  { label: 'GPA', path: 'education.0.gpa' },
  { label: '成绩排名', path: 'education.0.rank' },
  { label: '实验室', path: 'education.0.lab' },
  { label: '领域方向', path: 'education.0.research_direction' },
  { label: '导师', path: 'education.0.advisor' },
  { label: '论文', path: 'education.0.papers' },
  { label: '项目名称', path: 'projects.0.name' },
  { label: '项目角色', path: 'projects.0.role' },
  { label: '项目链接', path: 'projects.0.url' },
  { label: '项目描述', path: 'projects.0.description' },
]

export function valueAtProfilePath(profile: Record<string, unknown>, path: string) {
  return path.split('.').reduce<unknown>((target, part) => {
    if (target === undefined || target === null) return undefined
    const record = target as Record<string, unknown>
    return /^\d+$/.test(part) ? (target as unknown[])[Number(part)] : record[part]
  }, profile)
}

export function hasProfileValue(profile: Record<string, unknown>, path: string) {
  const value = valueAtProfilePath(profile, path)
  return Array.isArray(value) ? value.length > 0 : String(value || '').trim().length > 0
}

export function countFilledProfileFields(profile: Record<string, unknown>) {
  return profileRequiredFields.filter((item) => hasProfileValue(profile, item.path)).length
}
