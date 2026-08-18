import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import {
  createApplicationApi,
  createApplicationStatusEventApi,
  deleteApplicationApi,
  fetchApplicationsApi,
  updateApplicationApi,
} from '../api/applications'
import type {
  ApplicationStatus,
  ApplicationStatusEventPayload,
  BackendJobApplicationRecord,
  JobApplicationPayload,
  JobApplicationRecord,
} from '../types/application'

export const useApplicationStore = defineStore('application', () => {
  const applications = ref<JobApplicationRecord[]>([])
  const loading = ref(false)
  const saving = ref(false)
  const error = ref('')

  const totalCount = computed(() => applications.value.length)
  const activeCount = computed(() => applications.value.filter((item) => activeStatuses.has(item.status)).length)
  const rejectedCount = computed(
    () => applications.value.filter((item) => rejectedStatuses.has(item.status)).length,
  )
  const passedCount = computed(() => applications.value.filter((item) => item.status === 'passed' || item.status === 'offer').length)

  async function loadApplications() {
    loading.value = true
    try {
      applications.value = (await fetchApplicationsApi()).map(toApplicationRecord)
      error.value = ''
    } catch (err) {
      applications.value = []
      error.value = err instanceof Error ? err.message : String(err)
    } finally {
      loading.value = false
    }
  }

  async function createApplication(payload: JobApplicationPayload) {
    saving.value = true
    try {
      upsertApplication(toApplicationRecord(await createApplicationApi(payload)))
      error.value = ''
    } finally {
      saving.value = false
    }
  }

  async function updateApplication(id: number, payload: Partial<JobApplicationPayload>) {
    upsertApplication(toApplicationRecord(await updateApplicationApi(id, payload)))
  }

  async function updateStatus(id: number, status: ApplicationStatus) {
    await updateApplication(id, { status })
  }

  async function createStatusEvent(id: number, payload: ApplicationStatusEventPayload) {
    upsertApplication(toApplicationRecord(await createApplicationStatusEventApi(id, payload)))
  }

  async function deleteApplication(id: number) {
    await deleteApplicationApi(id)
    applications.value = applications.value.filter((item) => item.id !== id)
  }

  function upsertApplication(application: JobApplicationRecord) {
    const next = applications.value.filter((item) => item.id !== application.id)
    applications.value = [application, ...next].sort((a, b) => b.appliedDate.localeCompare(a.appliedDate) || b.id - a.id)
  }

  return {
    applications,
    loading,
    saving,
    error,
    totalCount,
    activeCount,
    rejectedCount,
    passedCount,
    loadApplications,
    createApplication,
    updateApplication,
    updateStatus,
    createStatusEvent,
    deleteApplication,
  }
})

const activeStatuses = new Set<ApplicationStatus>([
  'assessment',
  'written_test',
  'interviewing',
  'first_interview',
  'second_interview',
  'third_interview',
  'hr_interview',
  'offer',
])

const rejectedStatuses = new Set<ApplicationStatus>([
  'resume_rejected',
  'assessment_rejected',
  'written_test_rejected',
  'interview_rejected',
])

export function toApplicationRecord(record: BackendJobApplicationRecord): JobApplicationRecord {
  return {
    id: record.id,
    resumeId: record.resume_id,
    resumeFilename: record.resume_filename,
    company: record.company,
    position: record.position,
    appliedDate: record.applied_date,
    status: record.status,
    jobUrl: record.job_url,
    source: record.source,
    notes: record.notes,
    statusEvents: (record.status_events || []).map((event) => ({
      id: event.id,
      status: event.status,
      changedAt: event.changed_at,
      note: event.note,
      createdAt: event.created_at,
    })),
    createdAt: record.created_at,
    updatedAt: record.updated_at,
  }
}
