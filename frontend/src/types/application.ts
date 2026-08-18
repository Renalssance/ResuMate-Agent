export type ApplicationStatus =
  | 'applied'
  | 'assessment'
  | 'written_test'
  | 'interviewing'
  | 'first_interview'
  | 'second_interview'
  | 'third_interview'
  | 'hr_interview'
  | 'offer'
  | 'resume_rejected'
  | 'assessment_rejected'
  | 'written_test_rejected'
  | 'interview_rejected'
  | 'passed'
  | 'withdrawn'

export interface ApplicationStatusEvent {
  id: number
  status: ApplicationStatus
  changedAt: string
  note: string
  createdAt: string
}

export interface JobApplicationRecord {
  id: number
  resumeId: number | null
  resumeFilename: string
  company: string
  position: string
  appliedDate: string
  status: ApplicationStatus
  jobUrl: string
  source: string
  notes: string
  statusEvents: ApplicationStatusEvent[]
  createdAt: string
  updatedAt: string
}

export interface JobApplicationPayload {
  company: string
  position: string
  applied_date: string
  resume_id?: number | null
  status: ApplicationStatus
  job_url?: string
  source?: string
  notes?: string
}

export interface ApplicationStatusEventPayload {
  status: ApplicationStatus
  changed_at?: string
  note?: string
}

export interface BackendJobApplicationRecord extends JobApplicationPayload {
  id: number
  resume_id: number | null
  resume_filename: string
  job_url: string
  source: string
  notes: string
  status_events: Array<{
    id: number
    status: ApplicationStatus
    changed_at: string
    note: string
    created_at: string
  }>
  created_at: string
  updated_at: string
}

export const applicationStatusOptions: Array<{ value: ApplicationStatus; label: string }> = [
  { value: 'applied', label: '已投' },
  { value: 'assessment', label: '测评' },
  { value: 'written_test', label: '笔试' },
  { value: 'interviewing', label: '面试中' },
  { value: 'first_interview', label: '一面' },
  { value: 'second_interview', label: '二面' },
  { value: 'third_interview', label: '三面' },
  { value: 'hr_interview', label: 'HR 面' },
  { value: 'offer', label: 'Offer' },
  { value: 'resume_rejected', label: '简历挂' },
  { value: 'assessment_rejected', label: '测评挂' },
  { value: 'written_test_rejected', label: '笔试挂' },
  { value: 'interview_rejected', label: '面试挂' },
  { value: 'passed', label: '通过' },
  { value: 'withdrawn', label: '放弃' },
]

export function applicationStatusLabel(status: ApplicationStatus) {
  return applicationStatusOptions.find((item) => item.value === status)?.label || status
}
