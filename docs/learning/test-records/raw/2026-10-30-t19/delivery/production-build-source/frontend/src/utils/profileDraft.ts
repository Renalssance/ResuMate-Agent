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
