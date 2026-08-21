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
  isCompleted: boolean
}

export interface ScheduleNotePart {
  type: 'text' | 'link'
  value: string
}

export function buildApplicationScheduleItems(applications: ApplicationSource[]): ApplicationScheduleItem[] {
  return applications
    .flatMap((application) =>
      application.schedules.map((schedule) => ({
        ...schedule,
        status: schedule.status as ApplicationStatus,
        applicationLabel: `${application.company} · ${application.position}`,
        isCompleted: Boolean(schedule.completedEventId),
      })),
    )
    .sort((a, b) => new Date(a.startsAt).getTime() - new Date(b.startsAt).getTime() || a.id - b.id)
}

export function isScheduleToday(schedule: Pick<ApplicationScheduleItem, 'startsAt' | 'endsAt'>, now = new Date()) {
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  const startOfTomorrow = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1).getTime()
  return new Date(schedule.startsAt).getTime() < startOfTomorrow && new Date(schedule.endsAt).getTime() >= startOfToday
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
