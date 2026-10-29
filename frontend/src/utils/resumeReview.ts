import type { ArtifactReference, ReviewDecision, ResumeVersionArtifact, TailoringChange } from '../api/agentRuns'

export const resumeLabels: Record<string, string> = {
  self_summary: '个人简介', summary: '个人简介', content: '材料内容', answer: '补充经历', experience: '相关经历', work_experience: '工作经历', projects: '项目经历', bullets: '经历要点', target_role: '目标岗位', company: '公司', role: '岗位名称', description: '经历说明', period: '时间', highlights: '经历要点',
}
export const reviewLabels = { pending: '待审阅', accepted: '已接受', rejected: '保留原文', edited: '本人编辑' }
export function sectionLabel(section: string) {
  if (section === '/summary' || section === '/self_summary') return '个人简介'
  const match = /^\/(work_experience|projects)\/(\d+)\/description$/.exec(section)
  return match ? `${resumeLabels[match[1]!]} ${Number(match[2]) + 1} · 经历说明` : section
}
export function referenceKey(reference: ArtifactReference) {
  if (reference.kind === 'profile_fact') return `fact:${reference.factId}:${reference.revision}`
  if (reference.kind === 'applicant_answer') return `answer:${reference.actionId}`
  return `resume:${reference.resumeId}:${reference.inputVersion}:${reference.section}`
}
export function isRecord(value: unknown): value is Record<string, unknown> { return Boolean(value) && !Array.isArray(value) && typeof value === 'object' }
export function reviewChanges(artifact: Pick<ResumeVersionArtifact, 'structuredContent' | 'reviewable'> | null): TailoringChange[] | null {
  if (!artifact || artifact.reviewable === false) return null
  const content = artifact.structuredContent
  if (!isRecord(content.resume) || !isRecord(content.inputVersions) || !Array.isArray(content.changes)) return null
  return content.changes.every(change => isRecord(change) && typeof change.id === 'string' && typeof change.section === 'string'
    && typeof change.before === 'string' && (typeof change.after === 'string' || change.after === null)
    && typeof change.reason === 'string' && Array.isArray(change.fact_refs) && typeof change.requires_input === 'boolean'
    && typeof change.status === 'string' && change.status in reviewLabels && (change.status !== 'edited' || typeof change.editedText === 'string'))
    ? content.changes as TailoringChange[] : null
}
export function decisionsFor(changes: TailoringChange[]): Record<string, ReviewDecision> {
  return Object.fromEntries(changes.map(({ id, status, editedText }) => [id, status === 'edited' ? { id, status, editedText } : { id, status }]))
}
export function sameDecision(a: ReviewDecision | undefined, b: ReviewDecision | undefined) {
  return a?.status === b?.status && (a?.status !== 'edited' || a.editedText === b?.editedText)
}
export function projectResume(artifact: Pick<ResumeVersionArtifact, 'structuredContent' | 'reviewable'> | null, decisions: Record<string, ReviewDecision>): Record<string, unknown> {
  if (!artifact) return {}
  const changes = reviewChanges(artifact)
  if (!changes) return artifact.structuredContent
  const resume = JSON.parse(JSON.stringify(artifact.structuredContent.resume)) as Record<string, unknown>
  for (const change of changes) {
    const decision = decisions[change.id]
    const text = decision?.status === 'edited' ? decision.editedText! : decision?.status === 'accepted' ? change.after! : change.before
    const segments = change.section.slice(1).split('/')
    let target: unknown = resume
    for (const segment of segments.slice(0, -1)) target = (target as Record<string, unknown> | undefined)?.[segment]
    if (target && typeof target === 'object') {
      const field = segments.at(-1)!
      const record = target as Record<string, unknown>
      record[field] = text
      // Original parsed bullets are evidence, not a fallback for a deliberate replacement.
      if (field === 'description' && (decision?.status === 'accepted' || decision?.status === 'edited')) { delete record.bullets; delete record.metrics }
    }
  }
  return resume
}
