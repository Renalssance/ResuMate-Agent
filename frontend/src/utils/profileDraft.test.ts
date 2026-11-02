// @ts-expect-error Node's strip-types runner imports the TypeScript source directly.
const { normalizeProfile, fillProfileFromTemplate } = await import('./profileDraft.ts')

export {}

function assert(condition: unknown, message: string) {
  if (!condition) throw new Error(message)
}

const saved = {
  candidate_name: 'Ada',
  education: [{ school: 'Example University', papers: ['Existing paper'] }],
  papers: [{ name: 'New paper', publication_date: '2026.10', publisher: 'Example Journal', author_order: '第一作者', description: '研究介绍' }],
  achievements: [{ name: '竞赛一等奖', date: '2026.09', level: '国家级', source_refs: [{ chunk_id: 'c1' }] }],
}
const draft = normalizeProfile(saved)
assert(draft.papers[0].publisher === 'Example Journal' && draft.papers[0].author_order === '第一作者', 'paper details must survive loading saved data')
assert(draft.papers[0].publication_date === '2026.10' && draft.papers[0].description === '研究介绍', 'publication date and introduction must survive loading')
assert(draft.achievements[0].date === '2026.09' && draft.achievements[0].level === '国家级', 'award date and level must survive loading')
assert(draft.achievements[0].source_refs[0].chunk_id === 'c1', 'editing awards must preserve parsed provenance')
draft.papers[0].name = 'Edited paper'
assert(saved.papers[0].name === 'New paper', 'editing must not change the saved resume before save')
assert(draft.education[0].papers[0] === 'Existing paper', 'existing education paper lists must remain intact')

const parsed = normalizeProfile({ achievements: ['奖学金'] })
assert(parsed.achievements[0].name === '奖学金' && parsed.achievements[0].date === '', 'parsed string achievements must become editable awards')
assert(parsed.papers.length === 0, 'resumes without papers must start with an empty list')
const empty = normalizeProfile()
assert(empty.papers.length === 0 && empty.achievements.length === 0, 'new sections must be ready to add records on an empty resume')
console.log('Profile draft checks passed.')

const target = normalizeProfile({
  candidate_name: 'Ada', contact: { email: 'new@example.com', phone: '  ' },
  education: [{ school: 'B', major: 'Math' }, { school: 'A', major: 'CS', gpa: '4.0' }],
  projects: [{ name: 'New project', description: '' }],
  languages: ['中文'],
})
const template = normalizeProfile({
  candidate_name: 'Old name', contact: { email: 'old@example.com', phone: '123' },
  application: { expected_city: '上海' },
  education: [{ school: 'A', major: 'CS', gpa: '3.5', advisor: 'Prof A', source_refs: ['old'] }, { school: 'B', major: 'Math', advisor: 'Prof B' }],
  projects: [{ name: 'Old project', description: 'Old description' }],
  work_experience: [{ company: 'Company', title: 'Engineer', source_refs: ['old'] }],
  languages: ['English'], skills: [{ name: 'Python', source_refs: ['old'] }],
  raw_text: 'Do not copy',
})
const beforeTarget = JSON.stringify(target)
const beforeTemplate = JSON.stringify(template)
const result = fillProfileFromTemplate(target, template)
assert(result.profile.candidate_name === 'Ada' && result.profile.contact.email === 'new@example.com', 'template must not overwrite populated fields')
assert(result.profile.contact.phone === '123' && result.profile.application.expected_city === '上海', 'template must fill whitespace and missing nested fields')
assert(result.profile.education[0].advisor === 'Prof B' && result.profile.education[1].advisor === 'Prof A', 'reordered education must match by identity rather than position')
assert(result.profile.education[1].gpa === '4.0', 'existing experience details must survive')
assert(result.profile.projects.length === 1 && result.profile.projects[0].description === '', 'unrelated projects must not be combined or appended')
assert(result.profile.work_experience[0].company === 'Company', 'an empty section must receive template entries')
assert(result.profile.languages.join() === '中文' && result.profile.skills[0].name === 'Python', 'only empty value lists should be filled')
assert(!result.profile.raw_text && !result.profile.work_experience[0].source_refs && !result.profile.skills[0].source_refs && !result.profile.education[1].source_refs, 'source document metadata must not be copied')
assert(JSON.stringify(target) === beforeTarget && JSON.stringify(template) === beforeTemplate, 'applying a template must leave saved documents unchanged')
assert(result.changed && !fillProfileFromTemplate(result.profile, template).changed, 'reapplying a template must report no changes')
assert(fillProfileFromTemplate(normalizeProfile(), template).profile.projects[0].name === 'Old project', 'blank placeholder rows must count as empty sections')
const ambiguous = fillProfileFromTemplate(normalizeProfile({ education: [{ school: 'A' }] }), normalizeProfile({ education: [{ school: 'A', major: 'CS' }, { school: 'A', major: 'Math' }] }))
assert(ambiguous.profile.education[0].major === '', 'ambiguous repeated schools must not fill an arbitrary match')
const conflict = fillProfileFromTemplate(normalizeProfile({ education: [{ school: 'A', major: 'Math' }] }), template)
assert(conflict.profile.education[0].advisor === '', 'different degrees or majors at the same school must not be mixed')
console.log('Profile template checks passed.')
