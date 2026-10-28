import writeExcelFile, { type Row } from 'write-excel-file/universal'
import { applicationStatusLabel, type JobApplicationRecord } from '../types/application'

export function createApplicationExportBlob(applications: JobApplicationRecord[]): Promise<Blob> {
  const dateTimeFormat = new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
  const rows: Row[] = [
    ['公司名', '岗位', '投递链接', '投递时间线'].map((value) => ({
      value,
      fontWeight: 'bold',
      backgroundColor: '#E8F3EE',
    })),
    ...applications.map((application) => {
      const timeline = [...application.statusEvents]
        .sort((a, b) => new Date(a.changedAt).getTime() - new Date(b.changedAt).getTime())
        .map((event) => {
          const date = dateTimeFormat.format(new Date(event.changedAt))
          return `${date} · ${applicationStatusLabel(event.status)}${event.note ? ` · ${event.note}` : ''}`
        })
        .join('\n')

      return [application.company, application.position, application.jobUrl, timeline].map((value) => ({
        value,
        type: String,
        wrap: true,
        alignVertical: 'top' as const,
      }))
    }),
  ]

  return writeExcelFile(rows, {
    sheet: '投递记录',
    columns: [{ width: 24 }, { width: 32 }, { width: 55 }, { width: 85 }],
    stickyRowsCount: 1,
  }).toBlob()
}
