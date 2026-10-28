import type { ApplicationStatus } from '../types/application'

interface ScheduleSource {
  id: number
  applicationId: number
  status: string
  title: string
  startsAt: string
  endsAt: string
  note: string
  completedEventId: number | null
}

interface ApplicationSource {
  id: number
  company: string
  position: string
  schedules: ScheduleSource[]
}

export interface ApplicationScheduleItem extends Omit<ScheduleSource, 'status'> {
  status: ApplicationStatus
  applicationLabel: string
  companyShortName: string
  isCompleted: boolean
}

export type ScheduleCalendarPosition = 'single' | 'start' | 'middle' | 'end'

export interface ScheduleCalendarItem extends ApplicationScheduleItem {
  calendarPosition: ScheduleCalendarPosition
}

export interface ScheduleNotePart {
  type: 'text' | 'link'
  value: string
}

export interface ScheduleCalendarDay {
  key: string
  date: Date
  dayNumber: number
  isCurrentMonth: boolean
  isToday: boolean
  isPast: boolean
  schedules: ScheduleCalendarItem[]
}

export interface ScheduleCalendarCategory {
  key: 'written-test' | 'assessment' | 'interview' | 'other'
  label: string
}

export function buildApplicationScheduleItems(applications: ApplicationSource[]): ApplicationScheduleItem[] {
  return applications
    .flatMap((application) =>
      application.schedules.map((schedule) => ({
        ...schedule,
        status: schedule.status as ApplicationStatus,
        applicationLabel: `${application.company} · ${application.position}`,
        companyShortName: Array.from(application.company.trim()).slice(0, 2).join(''),
        isCompleted: Boolean(schedule.completedEventId),
      })),
    )
    .sort((a, b) => new Date(b.startsAt).getTime() - new Date(a.startsAt).getTime() || b.id - a.id)
}

export function buildScheduleCalendarDays(
  schedules: ApplicationScheduleItem[],
  month: Date,
  today = new Date(),
): ScheduleCalendarDay[] {
  const firstOfMonth = new Date(month.getFullYear(), month.getMonth(), 1)
  const mondayOffset = (firstOfMonth.getDay() + 6) % 7
  const gridStart = new Date(month.getFullYear(), month.getMonth(), 1 - mondayOffset)
  const daysInMonth = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate()
  const cellCount = Math.ceil((mondayOffset + daysInMonth) / 7) * 7
  const todayKey = formatLocalDateKey(today)
  const startOfToday = new Date(today.getFullYear(), today.getMonth(), today.getDate())

  return Array.from({ length: cellCount }, (_, index) => {
    const date = new Date(gridStart.getFullYear(), gridStart.getMonth(), gridStart.getDate() + index)
    const nextDate = new Date(date.getFullYear(), date.getMonth(), date.getDate() + 1)
    return {
      key: formatLocalDateKey(date),
      date,
      dayNumber: date.getDate(),
      isCurrentMonth: date.getMonth() === month.getMonth() && date.getFullYear() === month.getFullYear(),
      isToday: formatLocalDateKey(date) === todayKey,
      isPast: date < startOfToday,
      schedules: schedules
        .filter((schedule) => new Date(schedule.startsAt) < nextDate && new Date(schedule.endsAt) > date)
        .map((schedule) => ({
          ...schedule,
          calendarPosition: getScheduleCalendarPosition(schedule, date),
        }))
        .sort((a, b) => new Date(a.startsAt).getTime() - new Date(b.startsAt).getTime() || a.id - b.id),
    }
  })
}

function getScheduleCalendarPosition(
  schedule: Pick<ApplicationScheduleItem, 'startsAt' | 'endsAt'>,
  date: Date,
): ScheduleCalendarPosition {
  const dayKey = formatLocalDateKey(date)
  const startKey = formatLocalDateKey(new Date(schedule.startsAt))
  const occupiedEnd = new Date(new Date(schedule.endsAt).getTime() - 1)
  const endKey = formatLocalDateKey(occupiedEnd)

  if (startKey === endKey) return 'single'
  if (dayKey === startKey) return 'start'
  if (dayKey === endKey) return 'end'
  return 'middle'
}

export function getScheduleCalendarCategory(status: ApplicationStatus): ScheduleCalendarCategory {
  if (status === 'written_test') return { key: 'written-test', label: '笔试' }
  if (status === 'assessment') return { key: 'assessment', label: '测评' }
  if (['interviewing', 'first_interview', 'second_interview', 'third_interview', 'hr_interview'].includes(status)) {
    return { key: 'interview', label: '面试' }
  }
  return { key: 'other', label: '日程' }
}

export function formatLocalDateKey(date: Date) {
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${date.getFullYear()}-${month}-${day}`
}

export function isScheduleToday(schedule: Pick<ApplicationScheduleItem, 'startsAt' | 'endsAt'>, now = new Date()) {
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  const startOfTomorrow = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1).getTime()
  return new Date(schedule.startsAt).getTime() < startOfTomorrow && new Date(schedule.endsAt).getTime() > startOfToday
}

export function formatDateTimeRange(start: string, end: string) {
  const startDate = new Date(start)
  const endDate = new Date(end)
  const sameDay = startDate.getFullYear() === endDate.getFullYear()
    && startDate.getMonth() === endDate.getMonth()
    && startDate.getDate() === endDate.getDate()
  const dateTimeFormatter = new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
  const endFormatter = sameDay
    ? new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit' })
    : dateTimeFormatter

  return `${dateTimeFormatter.format(startDate)} - ${endFormatter.format(endDate)}`
}

export function buildScheduleNoteParts(note: string): ScheduleNotePart[] {
  const parts: ScheduleNotePart[] = []
  const urlPattern = /https?:\/\/\S+/g
  let cursor = 0

  for (const match of note.matchAll(urlPattern)) {
    const index = match.index ?? 0
    if (index > cursor) parts.push({ type: 'text', value: note.slice(cursor, index) })
    parts.push({ type: 'link', value: match[0] })
    cursor = index + match[0].length
  }

  if (cursor < note.length) parts.push({ type: 'text', value: note.slice(cursor) })
  return parts.length ? parts : [{ type: 'text', value: note }]
}
