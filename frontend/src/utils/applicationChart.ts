import type { ApplicationStatus, JobApplicationRecord } from '../types/application'

export interface ApplicationStatusSegment {
  key: 'active' | 'rejected' | 'passed' | 'other'
  label: string
  count: number
  percent: number
  tone: 'info' | 'danger' | 'success' | 'muted'
}

export type ApplicationStatusFilter = 'all' | 'active' | 'rejected' | 'passed'

const statusGroups: Array<Omit<ApplicationStatusSegment, 'count' | 'percent'> & { statuses: ApplicationStatus[] }> = [
  {
    key: 'active',
    label: '流程中',
    tone: 'info',
    statuses: ['assessment', 'written_test', 'interviewing', 'first_interview', 'second_interview', 'third_interview', 'hr_interview'],
  },
  {
    key: 'rejected',
    label: '已挂',
    tone: 'danger',
    statuses: ['resume_rejected', 'assessment_rejected', 'written_test_rejected', 'interview_rejected'],
  },
  {
    key: 'passed',
    label: 'Offer / 通过',
    tone: 'success',
    statuses: ['offer', 'passed'],
  },
  {
    key: 'other',
    label: '其他',
    tone: 'muted',
    statuses: ['applied', 'withdrawn'],
  },
]

export const applicationStatusFilterOptions: Array<{ value: ApplicationStatusFilter; label: string }> = [
  { value: 'all', label: '全部' },
  { value: 'active', label: '流程中' },
  { value: 'rejected', label: '已挂' },
  { value: 'passed', label: '通过' },
]

export function buildApplicationStatusSegments(applications: JobApplicationRecord[]): ApplicationStatusSegment[] {
  const total = applications.length
  return statusGroups.map((group) => {
    const count = applications.filter((item) => group.statuses.includes(item.status)).length
    return {
      key: group.key,
      label: group.label,
      tone: group.tone,
      count,
      percent: total ? Math.round(count / total * 100) : 0,
    }
  })
}

export function applicationMatchesStatusFilter(application: Pick<JobApplicationRecord, 'status'>, filter: ApplicationStatusFilter) {
  if (filter === 'all') return true
  return Boolean(statusGroups.find((group) => group.key === filter)?.statuses.includes(application.status))
}
