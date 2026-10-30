// @ts-expect-error Node's strip-types runner imports the TypeScript source directly.
const { applicationStatusFilterOptions, applicationMatchesStatusFilter, buildApplicationStatusSegments, buildApplicationSummary, buildApplicationMetricRecords } = await import('./applicationChart.ts')

export {}

function assert(condition: unknown, message: string) {
  if (!condition) throw new Error(message)
}

const base = {
  resumeId: null,
  resumeFilename: '',
  company: 'Acme',
  position: 'Engineer',
  appliedDate: '2026-08-01',
  jobUrl: '',
  source: '',
  notes: '',
  statusEvents: [],
  schedules: [],
  createdAt: '',
  updatedAt: '',
}

const summary = buildApplicationSummary([
  { ...base, id: 1, status: 'applied' },
  { ...base, company: ' Acme ', id: 2, status: 'assessment' },
  { ...base, company: 'Beta', id: 3, status: 'written_test' },
  ...(['interviewing', 'first_interview', 'second_interview', 'third_interview', 'hr_interview'] as const)
    .map((status, index) => ({ ...base, id: index + 4, status })),
  ...(['resume_rejected', 'assessment_rejected', 'written_test_rejected', 'interview_rejected'] as const)
    .map((status, index) => ({ ...base, id: index + 9, status })),
  { ...base, id: 13, status: 'offer' },
  { ...base, id: 14, status: 'passed' },
  { ...base, id: 15, status: 'withdrawn' },
])
assert(summary.companyCount === 2, 'multiple positions at the same company should count as one company')
assert(summary.assessmentCount === 2 && summary.writtenTestCount === 2, 'stage totals should include records that were rejected at that stage')
assert(summary.interviewCount === 6, 'interview total should include every interview round and interview rejections')
assert(summary.rejectedCount === 4 && summary.passedCount === 2, 'results should group all rejections and both offer and passed statuses')
assert(Object.values(summary.inProgress).every((count) => count === 0), 'recorded stages and applications without unfinished schedules must not be counted as in progress')
const { inProgress: emptyProgress, ...emptyTotals } = buildApplicationSummary([])
assert([...Object.values(emptyTotals), ...Object.values(emptyProgress)].every((count) => count === 0), 'empty applications should show zero for cumulative and in-progress metrics')

function statusEvent(status: ApplicationStatus, id: number): ApplicationStatusEvent {
  return { id, status, changedAt: '2026-10-01T10:00:00Z', note: '', createdAt: '' }
}

function schedule(status: ApplicationStatus, id: number, completedEventId: number | null): ApplicationSchedule {
  return {
    id, applicationId: 1, status, title: status,
    startsAt: '2026-10-01T09:00:00Z', endsAt: '2026-10-01T10:00:00Z',
    note: '', completedEventId, createdAt: '', updatedAt: '',
  }
}

const history: JobApplicationRecord[] = [
  { ...base, id: 1, status: 'passed', statusEvents: [
    statusEvent('assessment', 1), statusEvent('written_test', 2),
    statusEvent('first_interview', 3), statusEvent('second_interview', 4),
    statusEvent('offer', 5), statusEvent('passed', 6),
  ], schedules: [schedule('first_interview', 1, 3)] },
  { ...base, id: 2, status: 'written_test', statusEvents: [statusEvent('written_test', 7)],
    schedules: [schedule('written_test', 2, 7)] },
  { ...base, id: 3, company: 'Beta', status: 'second_interview',
    statusEvents: [statusEvent('first_interview', 8)],
    schedules: [schedule('first_interview', 3, 8), schedule('second_interview', 4, null)] },
  { ...base, id: 4, status: 'assessment', schedules: [schedule('assessment', 5, null)] },
  { ...base, id: 5, company: 'Gamma', status: 'withdrawn', statusEvents: [statusEvent('assessment', 9)] },
  { ...base, id: 6, company: 'Delta', status: 'assessment_rejected', schedules: [schedule('assessment', 6, null)] },
  { ...base, id: 7, company: 'Beta', status: 'applied',
    schedules: [schedule('assessment', 7, null), schedule('written_test', 8, null)] },
]
const historySummary = buildApplicationSummary(history)
assert(historySummary.companyCount === 4 && historySummary.inProgress.companyCount === 3, 'only companies with unfinished stage schedules should count as in progress')
assert(historySummary.assessmentCount === 5 && historySummary.inProgress.assessmentCount === 3, 'assessment progress should follow unfinished schedules independently of recorded results')
assert(historySummary.writtenTestCount === 3 && historySummary.inProgress.writtenTestCount === 1, 'completed schedules should count in totals without remaining in progress')
assert(historySummary.interviewCount === 2 && historySummary.inProgress.interviewCount === 1, 'multiple interview rounds and their linked events should count once per application')
assert(historySummary.rejectedCount === 1 && historySummary.passedCount === 1, 'offer and passed events for the same application should count as a single result')
assert(buildApplicationSummary([history[1]!]).inProgress.companyCount === 0, 'a company with only a completed schedule must not remain in progress')
assert(buildApplicationStatusSegments([history[1]!]).find((item: { key: string }) => item.key === 'active')?.count === 0, 'the status composition must not treat completed records as active')

const metricRecords = buildApplicationMetricRecords(history)
for (const [key, totalIds, activeIds] of [
  ['company', '1,2,3,4,5,6,7', '3,4,6,7'],
  ['assessment', '1,4,5,6,7', '4,6,7'],
  ['writtenTest', '1,2,7', '7'],
  ['interview', '1,3', '3'],
  ['rejected', '6', ''],
  ['passed', '1', ''],
] as const) {
  assert(metricRecords[key].total.map((item: JobApplicationRecord) => item.id).join(',') === totalIds,
    `${key} details should include every historical application once`)
  assert(metricRecords[key].inProgress.map((item: JobApplicationRecord) => item.id).join(',') === activeIds,
    `${key} details should highlight only applications still in that process`)
}
assert(Object.values(buildApplicationMetricRecords([])).every((item) => item.total.length === 0 && item.inProgress.length === 0), 'empty metrics should produce empty detail lists')

const segments = buildApplicationStatusSegments([
  { ...base, id: 1, status: 'applied' },
  { ...base, id: 2, status: 'interviewing', schedules: [schedule('interviewing', 9, null)] },
  { ...base, id: 3, status: 'offer' },
  { ...base, id: 4, status: 'resume_rejected' },
  { ...base, id: 5, status: 'withdrawn' },
])

assert(
  segments.map((item: { key: string }) => item.key).join(',') === 'active,rejected,passed,other',
  'status segments should keep the dashboard order',
)
assert(
  segments.map((item: { count: number }) => item.count).join(',') === '1,1,1,2',
  'application statuses should be counted into exclusive groups',
)
assert(
  segments.map((item: { percent: number }) => item.percent).join(',') === '20,20,20,40',
  'status segments should expose whole-number percentages',
)

const empty = buildApplicationStatusSegments([])
assert(empty.every((item: { count: number; percent: number }) => item.count === 0 && item.percent === 0), 'empty status segments should render as zeroes')

assert(
  applicationStatusFilterOptions.map((item: { label: string }) => item.label).join(',') === '全部,流程中,已挂,通过',
  'application filters should use dashboard-level categories',
)
assert(
  applicationMatchesStatusFilter({ status: 'first_interview', schedules: [] }, 'active') === false,
  'recorded interviews without unfinished schedules must not match the active filter',
)
assert(
  applicationMatchesStatusFilter({ status: 'applied', schedules: [schedule('written_test', 10, null)] }, 'active') === true,
  'unfinished stage schedules should match the active filter regardless of the recorded status',
)
assert(
  applicationMatchesStatusFilter({ status: 'written_test', schedules: [schedule('written_test', 11, 10)] }, 'active') === false,
  'completed schedules must leave the active filter even when the recorded stage is unchanged',
)
assert(
  applicationMatchesStatusFilter({ status: 'written_test_rejected', schedules: [] }, 'rejected') === true,
  'rejected filter should include rejection statuses',
)
assert(
  applicationMatchesStatusFilter({ status: 'offer', schedules: [] }, 'passed') === true,
  'passed filter should include offer statuses',
)
assert(
  applicationMatchesStatusFilter({ status: 'withdrawn', schedules: [] }, 'active') === false,
  'category filters should not include unrelated statuses',
)
import type { ApplicationStatus, ApplicationStatusEvent, ApplicationSchedule, JobApplicationRecord } from '../types/application'
