import { defineStore } from 'pinia'
import { ref } from 'vue'
import { analyzeFollowUpApi } from '../api/followUp'
import type { DocumentRecord } from '../types/document'
import type { FollowUpSession } from '../types/followUp'
import type { QuestionSet } from '../types/question'
import { createId } from '../utils/format'

export const useFollowUpStore = defineStore('followUp', () => {
  const session = ref<FollowUpSession | null>(null)
  const jdContext = ref<Record<string, unknown>>({})
  const resumeContext = ref<Record<string, unknown>>({})
  const questionContext = ref<Record<string, unknown>>({})
  const loading = ref(false)
  const error = ref('')

  function startSession(jd: DocumentRecord, resume: DocumentRecord, questionSet?: QuestionSet, initialQuestion?: string) {
    const firstQuestion = questionSet?.questions[0]
    const question =
      initialQuestion ||
      firstQuestion?.title ||
      'Please introduce one project that best demonstrates your fit for this role.'

    jdContext.value = jd.parsedContent || {}
    resumeContext.value = resume.parsedContent || {}
    questionContext.value = firstQuestion
      ? {
          title: firstQuestion.title,
          focus: firstQuestion.focus,
          evidence: firstQuestion.evidence,
          idealAnswer: firstQuestion.idealAnswer,
          rubric: firstQuestion.rubric,
        }
      : {}

    session.value = {
      id: createId('session'),
      jdId: jd.id,
      resumeId: resume.id,
      questionSetId: questionSet?.id,
      currentAbility: firstQuestion?.focus?.join(' / ') || 'Role fit and evidence clarity',
      coveredQuestions: [question],
      nextSuggestion: 'Wait for the candidate answer, then generate a targeted follow-up.',
      rounds: [
        {
          id: createId('round'),
          question,
          answer: '',
          followUp: '',
          reason: '',
          evidence: firstQuestion?.evidence ? [firstQuestion.evidence] : [],
          risks: [],
        },
      ],
    }
  }

  async function submitAnswer(answer: string) {
    if (!session.value) return
    const lastRound = session.value.rounds[session.value.rounds.length - 1]
    if (!lastRound) return

    loading.value = true
    error.value = ''
    try {
      const result = await analyzeFollowUpApi({
        question: lastRound.question,
        answer,
        jd_context: jdContext.value,
        resume_context: resumeContext.value,
        question_context: questionContext.value,
        history: session.value.rounds.map((round) => ({
          question: round.question,
          answer: round.answer,
          follow_up: round.followUp,
          reason: round.reason,
        })),
      })
      lastRound.answer = answer
      lastRound.followUp = result.follow_up
      lastRound.reason = result.reason
      lastRound.evidence = result.evidence
      lastRound.risks = result.risks
      session.value.currentAbility = result.current_ability
      session.value.nextSuggestion = result.next_suggestion
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
      throw err
    } finally {
      loading.value = false
    }
  }

  function appendNextRound() {
    if (!session.value) return
    const last = session.value.rounds[session.value.rounds.length - 1]
    if (!last.followUp) return
    session.value.coveredQuestions.push(last.followUp)
    session.value.rounds.push({
      id: createId('round'),
      question: last.followUp,
      answer: '',
      followUp: '',
      reason: '',
      evidence: [],
      risks: [],
    })
  }

  return { session, loading, error, startSession, submitAnswer, appendNextRound }
})
