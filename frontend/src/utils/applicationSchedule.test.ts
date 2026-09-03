// @ts-expect-error Node's strip-types runner imports the TypeScript source directly.
const { buildApplicationScheduleItems, buildScheduleNoteParts, isScheduleToday } = await import('./applicationSchedule.ts')

export {}

function assert(condition: unknown, message: string) {
  if (!condition) throw new Error(message)
}

const base = {
  resumeId: null,
  resumeFilename: '',
  appliedDate: '2026-08-01',
  status: 'applied',
  jobUrl: '',
  source: '',
  notes: '',
  statusEvents: [],
  createdAt: '',
  updatedAt: '',
}

const applications = [
  {
    ...base,
    id: 1,
    company: 'ByteDance',
    position: '后端开发',
    schedules: [
      {
        id: 11,
        applicationId: 1,
        status: 'written_test',
        title: '在线笔试',
        startsAt: '2026-08-23T10:00:00Z',
        endsAt: '2026-08-23T11:40:00Z',
        note: '提前登录',
        completedEventId: null,
        createdAt: '',
        updatedAt: '',
      },
    ],
  },
  {
    ...base,
    id: 2,
    company: 'Tencent',
    position: '平台开发',
    schedules: [
      {
        id: 21,
        applicationId: 2,
        status: 'first_interview',
        title: '一面',
        startsAt: '2026-08-22T15:00:00Z',
        endsAt: '2026-08-22T16:00:00Z',
        note: '',
        completedEventId: 5,
        createdAt: '',
        updatedAt: '',
      },
    ],
  },
]

const items = buildApplicationScheduleItems(applications)

assert(
  items.map((item: { id: number }) => item.id).join(',') === '11,21',
  'schedule items should be sorted by newest start time across applications',
)
assert(
  items[0].applicationLabel === 'ByteDance · 后端开发',
  'schedule items should carry the linked application label',
)
assert(
  items[0].isCompleted === false && items[1].isCompleted === true,
  'schedule items should expose whether they have been written to the timeline',
)
assert(
  isScheduleToday(items[0], new Date('2026-08-23T09:00:00+08:00')) === true,
  'schedule items should be treated as today in the viewer local day',
)
assert(
  isScheduleToday(items[0], new Date('2026-08-24T09:00:00+08:00')) === false,
  'schedule items should not stay highlighted after their local day',
)

const noteParts = buildScheduleNoteParts('入口 https://interview.antgroup.com/home/candidateExam?token=b978 提前登录')

assert(
  JSON.stringify(noteParts) === JSON.stringify([
    { type: 'text', value: '入口 ' },
    { type: 'link', value: 'https://interview.antgroup.com/home/candidateExam?token=b978' },
    { type: 'text', value: ' 提前登录' },
  ]),
  'schedule notes should expose web links as clickable parts without losing surrounding text',
)
