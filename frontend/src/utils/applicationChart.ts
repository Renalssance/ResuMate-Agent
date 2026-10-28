import type { ApplicationStatus, JobApplicationRecord } from '../types/application'

export interface ApplicationStatusSegment {
  key: 'active' | 'rejected' | 'passed' | 'other'
  label: string
  count: number
  percent: number
  tone: 'info' | 'danger' | 'success' | 'muted'
}

export type ApplicationStatusFilter = 'all' | 'active' | 'rejected' | 'passed'
export type ApplicationMetricKey = 'company' | 'assessment' | 'writtenTest' | 'interview' | 'rejected' | 'passed'

const processStatuses: ApplicationStatus[] = [
  'assessment', 'written_test', 'interviewing', 'first_interview', 'second_interview', 'third_interview', 'hr_interview',
]

const statusGroups: Array<Omit<ApplicationStatusSegment, 'count' | 'percent'> & { statuses: ApplicationStatus[] }> = [
  {
    key: 'active',
    label: '流程中',
    tone: 'info',
    statuses: processStatuses,
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
  const currentGroups = applications.map((item) => {
    if (applicationMatchesStatusFilter(item, 'rejected')) return 'rejected'
    if (applicationMatchesStatusFilter(item, 'passed')) return 'passed'
    return hasPendingSchedule(item) ? 'active' : 'other'
  })
  return statusGroups.map((group) => {
    const count = currentGroups.filter((key) => key === group.key).length
    return {
      key: group.key,
      label: group.label,
      tone: group.tone,
      count,
      percent: total ? Math.round(count / total * 100) : 0,
    }
  })
}

export function buildApplicationMetricRecords(applications: JobApplicationRecord[]) {
  const activeApplications = applications.filter((item) => hasPendingSchedule(item))
  function hasHistory(item: JobApplicationRecord, statuses: ApplicationStatus[]) {
    return statuses.includes(item.status)
      || item.statusEvents.some((event) => statuses.includes(event.status))
      || item.schedules.some((schedule) => statuses.includes(schedule.status))
  }
  function stageRecords(statuses: ApplicationStatus[], rejection: ApplicationStatus) {
    return {
      total: applications.filter((item) => hasHistory(item, [...statuses, rejection])),
      inProgress: applications.filter((item) => hasPendingSchedule(item, statuses)),
    }
  }
  return {
    company: { total: applications, inProgress: activeApplications },
    assessment: stageRecords(['assessment'], 'assessment_rejected'),
    writtenTest: stageRecords(['written_test'], 'written_test_rejected'),
    interview: stageRecords(
      ['interviewing', 'first_interview', 'second_interview', 'third_interview', 'hr_interview'],
      'interview_rejected',
    ),
    rejected: {
      total: applications.filter((item) => hasHistory(item, statusGroups.find((group) => group.key === 'rejected')!.statuses)),
      inProgress: [] as JobApplicationRecord[],
    },
    passed: {
      total: applications.filter((item) => hasHistory(item, ['offer', 'passed'])),
      inProgress: [] as JobApplicationRecord[],
    },
  }
}

export function buildApplicationSummary(applications: JobApplicationRecord[]) {
  const records = buildApplicationMetricRecords(applications)
  return {
    companyCount: new Set(applications.map((item) => item.company.trim())).size,
    assessmentCount: records.assessment.total.length,
    writtenTestCount: records.writtenTest.total.length,
    interviewCount: records.interview.total.length,
    rejectedCount: records.rejected.total.length,
    passedCount: records.passed.total.length,
    inProgress: {
      companyCount: new Set(records.company.inProgress.map((item) => item.company.trim())).size,
      assessmentCount: records.assessment.inProgress.length,
      writtenTestCount: records.writtenTest.inProgress.length,
      interviewCount: records.interview.inProgress.length,
    },
  }
}

function hasPendingSchedule(application: Pick<JobApplicationRecord, 'schedules'>, statuses = processStatuses) {
  return application.schedules.some((schedule) =>
    schedule.completedEventId === null && statuses.includes(schedule.status),
  )
}

export function applicationMatchesStatusFilter(application: Pick<JobApplicationRecord, 'status' | 'schedules'>, filter: ApplicationStatusFilter) {
  if (filter === 'all') return true
  if (filter === 'active') return hasPendingSchedule(application)
  return Boolean(statusGroups.find((group) => group.key === filter)?.statuses.includes(application.status))
}
