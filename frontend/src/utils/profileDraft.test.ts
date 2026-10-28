// @ts-expect-error Node's strip-types runner imports the TypeScript source directly.
const { normalizeProfile } = await import('./profileDraft.ts')

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
