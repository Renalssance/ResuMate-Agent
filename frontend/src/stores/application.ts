import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import {
  createApplicationApi,
  createApplicationScheduleApi,
  createApplicationStatusEventApi,
  completeApplicationScheduleApi,
  deleteApplicationApi,
  fetchApplicationsApi,
  updateApplicationApi,
} from '../api/applications'
import type {
  ApplicationSchedulePayload,
  ApplicationStatus,
  ApplicationStatusEventPayload,
  BackendJobApplicationRecord,
  JobApplicationPayload,
  JobApplicationRecord,
} from '../types/application'
import { buildApplicationStatusSegments } from '../utils/applicationChart'

export const useApplicationStore = defineStore('application', () => {
  const applications = ref<JobApplicationRecord[]>([])
  const loading = ref(false)
  const saving = ref(false)
  const error = ref('')

  const statusSegments = computed(() => buildApplicationStatusSegments(applications.value))
  const totalCount = computed(() => applications.value.length)
  const activeCount = computed(() => segmentCount(statusSegments.value, 'active'))
  const rejectedCount = computed(() => segmentCount(statusSegments.value, 'rejected'))
  const passedCount = computed(() => segmentCount(statusSegments.value, 'passed'))

  async function loadApplications() {
    loading.value = true
    try {
      applications.value = (await fetchApplicationsApi()).map(toApplicationRecord)
      error.value = ''
    } catch (err) {
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
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
      throw err
    } finally {
      saving.value = false
    }
  }

  async function updateApplication(id: number, payload: Partial<JobApplicationPayload>) {
    saving.value = true
    error.value = ''
    try {
      upsertApplication(toApplicationRecord(await updateApplicationApi(id, payload)))
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
      throw err
    } finally {
      saving.value = false
    }
  }

  async function updateStatus(id: number, status: ApplicationStatus) {
    await updateApplication(id, { status })
  }

  async function createStatusEvent(id: number, payload: ApplicationStatusEventPayload) {
    saving.value = true
    error.value = ''
    try {
      upsertApplication(toApplicationRecord(await createApplicationStatusEventApi(id, payload)))
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
      throw err
    } finally {
      saving.value = false
    }
  }

  async function createSchedule(id: number, payload: ApplicationSchedulePayload) {
    saving.value = true
    error.value = ''
    try {
      upsertApplication(toApplicationRecord(await createApplicationScheduleApi(id, payload)))
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
      throw err
    } finally {
      saving.value = false
    }
  }

  async function completeSchedule(id: number, scheduleId: number) {
    upsertApplication(toApplicationRecord(await completeApplicationScheduleApi(id, scheduleId)))
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
    createSchedule,
    completeSchedule,
    deleteApplication,
  }
})

function segmentCount(segments: ReturnType<typeof buildApplicationStatusSegments>, key: 'active' | 'rejected' | 'passed') {
  return segments.find((item) => item.key === key)?.count || 0
}

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
    schedules: (record.schedules || []).map((schedule) => ({
      id: schedule.id,
      applicationId: schedule.application_id,
      status: schedule.status,
      title: schedule.title,
      startsAt: schedule.starts_at,
      endsAt: schedule.ends_at,
      note: schedule.note,
      completedEventId: schedule.completed_event_id,
      createdAt: schedule.created_at,
      updatedAt: schedule.updated_at,
    })),
    createdAt: record.created_at,
    updatedAt: record.updated_at,
  }
}
