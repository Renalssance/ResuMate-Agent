type AnyRecord = Record<string, any>

export function emptyProfile(): AnyRecord {
  return {
    candidate_name: '',
    contact: {},
    application: {},
    education: [emptyEducation()],
    work_experience: [],
    projects: [emptyProject()],
    papers: [],
    achievements: [],
    skills: [],
    languages: [],
    certifications: [],
    self_summary: '',
  }
}

export function emptyEducation(): AnyRecord {
  return { school: '', college: '', degree: '', major: '', gpa: '', rank: '', years: '', start_date: '', end_date: '', lab: '', research_direction: '', advisor: '', papers: '' }
}

export function emptyWork(): AnyRecord {
  return { company: '', title: '', duration: '', start_date: '', end_date: '', description: '' }
}

export function emptyProject(): AnyRecord {
  return { name: '', role: '', duration: '', start_date: '', end_date: '', url: '', description: '' }
}

export function emptyPaper(): AnyRecord {
  return { name: '', publication_date: '', publisher: '', author_order: '', description: '' }
}

export function emptyAward(): AnyRecord {
  return { name: '', date: '', level: '' }
}

export function normalizeProfile(input: Record<string, unknown> = {}): AnyRecord {
  const copy = JSON.parse(JSON.stringify(input || {}))
  const profile = { ...emptyProfile(), ...copy }
  profile.contact = { ...(copy.contact || {}) }
  profile.application = { ...(copy.application || {}) }
  profile.education = ensureArray(copy.education).map((item) => ({ ...emptyEducation(), ...item }))
  if (!profile.education.length) profile.education = [emptyEducation()]
  profile.work_experience = ensureArray(copy.work_experience || copy.experience).map((item) => ({ ...emptyWork(), ...item }))
  profile.projects = ensureArray(copy.projects).map((item) => ({ ...emptyProject(), ...item }))
  if (!profile.projects.length) profile.projects = [emptyProject()]
  profile.papers = ensureArray(copy.papers).map((item) => ({ ...emptyPaper(), ...item }))
  profile.achievements = ensureArray(copy.achievements).map((item) => ({
    ...emptyAward(),
    ...(typeof item === 'string' ? { name: item } : item),
  }))
  profile.skills = ensureArray(copy.skills)
  profile.languages = ensureArray(copy.languages)
  profile.certifications = ensureArray(copy.certifications)
  return profile
}

function ensureArray(value: unknown): AnyRecord[] {
  return Array.isArray(value) ? value as AnyRecord[] : []
}

/** Fill editable values only; document provenance always belongs to the target. */
export function fillProfileFromTemplate(target: AnyRecord, template: AnyRecord) {
  const profile = normalizeProfile(target)
  const source = normalizeProfile(template)
  let changed = false
  const blank = (value: any): boolean => value == null
    || (typeof value === 'string' && !value.trim())
    || (Array.isArray(value) && value.every(blank))
  const clone = (value: any) => JSON.parse(JSON.stringify(value))
  function fillFields(destination: AnyRecord, from: AnyRecord, keys: string[]) {
    for (const key of keys) {
      if (blank(destination[key]) && !blank(from[key])) {
        destination[key] = clone(from[key])
        changed = true
      }
    }
  }
  fillFields(profile, source, ['candidate_name', 'self_summary'])
  fillFields(profile.contact, source.contact, ['email', 'phone', 'location', 'wechat'])
  fillFields(profile.application, source.application, [
    'gender', 'birth_date', 'nationality', 'political_status', 'native_place',
    'hukou_location', 'ethnicity', 'referral_code', 'expected_city', 'expected_position',
    'expected_salary', 'earliest_start_date', 'current_address', 'portfolio_url',
    'github_url', 'linkedin_url', 'emergency_contact_name', 'emergency_contact_phone',
    'id_document_type', 'id_number',
  ])
  const sections = [
    { key: 'education', fields: emptyEducation(), identity: ['school', 'major', 'degree', 'start_date', 'end_date'] },
    { key: 'work_experience', fields: emptyWork(), identity: ['company', 'title', 'start_date', 'end_date'] },
    { key: 'projects', fields: emptyProject(), identity: ['name', 'start_date', 'end_date'] },
    { key: 'papers', fields: emptyPaper(), identity: ['name', 'publication_date'] },
    { key: 'achievements', fields: emptyAward(), identity: ['name', 'date'] },
  ]
  for (const { key, fields, identity } of sections) {
    const keys = Object.keys(fields)
    const rows = source[key].filter((row: AnyRecord) => keys.some((field) => !blank(row[field])))
    if (!rows.length) continue
    if (profile[key].every((row: AnyRecord) => keys.every((field) => blank(row[field])))) {
      profile[key] = rows.map((row: AnyRecord) => {
        const entry = { ...fields }
        fillFields(entry, row, keys)
        return entry
      })
      continue
    }
    for (const row of profile[key]) {
      const primary = identity[0]!
      if (blank(row[primary])) continue
      const matches = rows.filter((candidate: AnyRecord) =>
        String(row[primary]).trim() === String(candidate[primary] ?? '').trim()
        && identity.every((field) => blank(row[field]) || blank(candidate[field])
          || String(row[field]).trim() === String(candidate[field]).trim()))
      if (matches.length === 1) fillFields(row, matches[0], keys)
    }
  }
  fillFields(profile, source, ['languages', 'certifications'])
  if (profile.skills.every((item: any) => blank(typeof item === 'string' ? item : item.name))) {
    const skills = source.skills.map((item: any) => typeof item === 'string' ? item : { name: item.name })
      .filter((item: any) => !blank(typeof item === 'string' ? item : item.name))
    if (skills.length) {
      profile.skills = skills
      changed = true
    }
  }
  return { profile, changed }
}
