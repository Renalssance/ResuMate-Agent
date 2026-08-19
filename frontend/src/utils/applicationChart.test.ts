// @ts-expect-error Node's strip-types runner imports the TypeScript source directly.
const { buildApplicationStatusSegments } = await import('./applicationChart.ts')

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
  createdAt: '',
  updatedAt: '',
}

const segments = buildApplicationStatusSegments([
  { ...base, id: 1, status: 'applied' },
  { ...base, id: 2, status: 'interviewing' },
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
