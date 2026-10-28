// @ts-expect-error Node's strip-types runner imports the TypeScript source directly.
const applicationSchedule = await import('./applicationSchedule.ts')
const {
  buildApplicationScheduleItems,
  buildScheduleCalendarDays,
  buildScheduleNoteParts,
  formatDateTimeRange,
  getScheduleCalendarCategory,
  isScheduleToday,
} = applicationSchedule

export {}

function assert(condition: unknown, message: string) {
  if (!condition) throw new Error(message)
}

function localIso(year: number, month: number, day: number, hour: number, minute = 0) {
  return new Date(year, month - 1, day, hour, minute).toISOString()
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
  items[0].companyShortName === 'By' && items[1].companyShortName === 'Te',
  'schedule items should expose the first two company characters for calendar linking markers',
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

assert(
  formatDateTimeRange(localIso(2026, 9, 17, 19), localIso(2026, 9, 17, 21)) === '09/17 19:00 - 21:00',
  'same-day schedules should omit the repeated end date',
)

assert(
  formatDateTimeRange(localIso(2026, 9, 16, 18, 26), localIso(2026, 9, 17, 1, 26)) === '09/16 18:26 - 09/17 01:26',
  'cross-day schedules should display both dates',
)

const calendarItems = buildApplicationScheduleItems([
  {
    ...base,
    id: 3,
    company: 'Xpeng',
    position: 'Data Infra',
    schedules: [
      {
        id: 31,
        applicationId: 3,
        status: 'assessment',
        title: 'AI 测评面试',
        startsAt: localIso(2026, 8, 23, 23),
        endsAt: localIso(2026, 8, 25, 1),
        note: '',
        completedEventId: null,
      },
      {
        id: 32,
        applicationId: 3,
        status: 'written_test',
        title: '午夜结束的笔试',
        startsAt: localIso(2026, 8, 25, 23),
        endsAt: localIso(2026, 8, 26, 0),
        note: '',
        completedEventId: null,
      },
    ],
  },
])
const calendarDays = buildScheduleCalendarDays(calendarItems, new Date(2026, 7, 12, 12), new Date(2026, 7, 23, 9))

assert(
  calendarDays.length === 42 && calendarDays[0].key === '2026-07-27' && calendarDays[41].key === '2026-09-06',
  'six-week months should contain every Monday-first calendar date',
)
assert(
  buildScheduleCalendarDays([], new Date(2026, 8, 12, 12)).length === 35,
  'five-week months should not render an empty sixth week',
)
assert(
  calendarDays.find((day: { key: string }) => day.key === '2026-08-23')?.isToday === true,
  'month calendars should identify the viewer local today',
)
assert(
  calendarDays.find((day: { key: string }) => day.key === '2026-08-22')?.isPast === true
    && calendarDays.find((day: { key: string }) => day.key === '2026-08-23')?.isPast === false
    && calendarDays.find((day: { key: string }) => day.key === '2026-08-24')?.isPast === false,
  'month calendars should identify dates before today as past',
)
assert(
  ['2026-08-23', '2026-08-24', '2026-08-25'].every((key) =>
    calendarDays.find((day: { key: string }) => day.key === key)?.schedules.some((schedule: { id: number }) => schedule.id === 31),
  ) && !calendarDays.find((day: { key: string }) => day.key === '2026-08-26')?.schedules.some((schedule: { id: number }) => schedule.id === 31),
  'cross-day schedules should appear on every covered calendar date',
)
assert(
  calendarDays.find((day: { key: string }) => day.key === '2026-08-25')?.schedules.some((schedule: { id: number }) => schedule.id === 32)
    && !calendarDays.find((day: { key: string }) => day.key === '2026-08-26')?.schedules.some((schedule: { id: number }) => schedule.id === 32),
  'schedules ending at midnight should not occupy the following date',
)
assert(
  JSON.stringify(
    ['2026-08-23', '2026-08-24', '2026-08-25'].map((key) => {
      const schedule = calendarDays
        .find((day: { key: string }) => day.key === key)
        ?.schedules.find((item: { id: number }) => item.id === 31)
      return [schedule?.calendarPosition, schedule?.companyShortName]
    }),
  ) === JSON.stringify([
    ['start', 'Xp'],
    ['middle', 'Xp'],
    ['end', 'Xp'],
  ]),
  'multi-day schedules should link their start, middle and end markers with the company short name',
)
assert(
  calendarDays
    .find((day: { key: string }) => day.key === '2026-08-25')
    ?.schedules.find((schedule: { id: number }) => schedule.id === 32)
    ?.calendarPosition === 'single',
  'a schedule ending at midnight should remain a single-day capsule on its only occupied date',
)

assert(
  JSON.stringify([
    getScheduleCalendarCategory('written_test'),
    getScheduleCalendarCategory('assessment'),
    getScheduleCalendarCategory('first_interview'),
    getScheduleCalendarCategory('hr_interview'),
  ]) === JSON.stringify([
    { key: 'written-test', label: '笔试' },
    { key: 'assessment', label: '测评' },
    { key: 'interview', label: '面试' },
    { key: 'interview', label: '面试' },
  ]),
  'calendar capsules should normalize schedule statuses into stable categories',
)
