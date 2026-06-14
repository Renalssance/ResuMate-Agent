import { computed, onBeforeUnmount, ref } from 'vue'
import { closeTaskProgress, subscribeTaskProgress } from '../services/sse'
import type { ProgressStep, SseProgressEvent, StepTemplate, TaskStatus } from '../types/task'

export function useTaskSse(stepTemplates: StepTemplate[]) {
  const taskId = ref('')
  const status = ref<TaskStatus>('pending')
  const progress = ref(0)
  const currentStage = ref('')
  const message = ref('')
  const errorReason = ref('')
  const steps = ref<ProgressStep[]>(createSteps(stepTemplates))

  const completedSteps = computed(() => steps.value.filter((step) => step.status === 'success'))
  const currentStep = computed(() => steps.value.find((step) => step.status === 'running')?.label || currentStage.value)

  function start(id: string) {
    reset()
    taskId.value = id
    subscribeTaskProgress(id, {
      onMessage: handleMessage,
      onError: (error) => {
        status.value = 'failed'
        errorReason.value = error.message
      },
    })
  }

  function startManual(id: string, messageText = 'Task submitted to backend') {
    reset()
    taskId.value = id
    status.value = 'running'
    progress.value = 8
    const firstStep = steps.value[0]
    currentStage.value = firstStep?.key || 'running'
    message.value = messageText
    steps.value = steps.value.map((step, index) =>
      index === 0 ? { ...step, status: 'running', progress: 20, message: messageText } : step,
    )
  }

  function completeManual(messageText = 'Backend task completed') {
    status.value = 'success'
    progress.value = 100
    currentStage.value = 'completed'
    message.value = messageText
    steps.value = steps.value.map((step) => ({ ...step, status: 'success', progress: 100, message: step.message }))
  }

  function failManual(reason: string) {
    status.value = 'failed'
    progress.value = Math.max(progress.value, 80)
    errorReason.value = reason
    message.value = reason
    const activeIndex = steps.value.findIndex((step) => step.status === 'running')
    steps.value = steps.value.map((step, index) =>
      index === (activeIndex >= 0 ? activeIndex : 0)
        ? { ...step, status: 'failed', progress: 100, message: reason }
        : step,
    )
  }

  function handleMessage(event: SseProgressEvent) {
    status.value = event.status
    progress.value = event.progress
    currentStage.value = event.stage
    message.value = event.message
    if (event.status === 'failed') errorReason.value = event.message

    const activeIndex = steps.value.findIndex((step) => step.key === event.stage)
    steps.value = steps.value.map((step, index) => {
      if (event.stage === 'completed') {
        return { ...step, status: 'success', progress: 100 }
      }
      if (index < activeIndex) {
        return { ...step, status: 'success', progress: 100 }
      }
      if (index === activeIndex) {
        return {
          ...step,
          status: event.status === 'failed' ? 'failed' : event.status === 'success' ? 'success' : 'running',
          progress: event.status === 'failed' ? event.progress : Math.max(step.progress, event.progress),
          message: event.message,
        }
      }
      return step
    })
  }

  function reset() {
    if (taskId.value) closeTaskProgress(taskId.value)
    taskId.value = ''
    status.value = 'pending'
    progress.value = 0
    currentStage.value = ''
    message.value = ''
    errorReason.value = ''
    steps.value = createSteps(stepTemplates)
  }

  onBeforeUnmount(reset)

  return {
    taskId,
    status,
    progress,
    currentStage,
    currentStep,
    message,
    errorReason,
    steps,
    completedSteps,
    start,
    startManual,
    completeManual,
    failManual,
    reset,
  }
}

function createSteps(templates: StepTemplate[]): ProgressStep[] {
  return templates.map((step) => ({
    ...step,
    status: 'pending',
    progress: 0,
  }))
}
