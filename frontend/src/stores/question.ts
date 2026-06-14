import { defineStore } from 'pinia'
import { ref } from 'vue'
import { fetchCandidateReportApi, generateCandidateQuestionsApi } from '../api/runs'
import { getReportForMatch } from './match'
import type { DocumentRecord } from '../types/document'
import type { MatchResult } from '../types/match'
import type { QuestionSet } from '../types/question'
import type { CandidateReport, EvidenceChunk, InterviewQuestion as ReportQuestion } from '../types/run'
import { createId } from '../utils/format'

export const useQuestionStore = defineStore('question', () => {
  const questionSets = ref<QuestionSet[]>([])
  const loading = ref(false)
  const error = ref('')

  function loadQuestionSets(matches: MatchResult[] = []) {
    loading.value = false
    error.value = ''
    questionSets.value = matches.flatMap((match) => {
      const report = getReportForMatch(match.id)
      return report?.formal_questions.length ? [buildQuestionSetFromReport(null, null, report.formal_questions, report.formal_questions.length, match, report)] : []
    })
  }

  async function createQuestionSet(jd: DocumentRecord, resume: DocumentRecord, count: number, match: MatchResult, taskId = '') {
    loading.value = true
    error.value = ''
    try {
      const sourceReport = await generateQuestionsForMatch(match, taskId)
      const created = buildQuestionSetFromReport(jd, resume, sourceReport.formal_questions, count, match, sourceReport)
      questionSets.value = [created, ...questionSets.value]
      return { questionSetId: created.id }
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
      throw err
    } finally {
      loading.value = false
    }
  }

  async function deleteQuestionSet(id: string) {
    questionSets.value = questionSets.value.filter((set) => set.id !== id)
  }

  async function restoreQuestionSet(jd: DocumentRecord, resume: DocumentRecord, count: number, match: MatchResult) {
    loading.value = true
    error.value = ''
    try {
      const sourceReport = await fetchQuestionsForMatch(match)
      const restored = buildQuestionSetFromReport(jd, resume, sourceReport.formal_questions, count, match, sourceReport)
      questionSets.value = [restored, ...questionSets.value]
      return { questionSetId: restored.id }
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
      throw err
    } finally {
      loading.value = false
    }
  }

  return { questionSets, loading, error, loadQuestionSets, createQuestionSet, restoreQuestionSet, deleteQuestionSet }
})

async function generateQuestionsForMatch(match: MatchResult, taskId = ''): Promise<CandidateReport> {
  const [runId, candidateId] = match.id.split(':')
  if (!runId || !candidateId) throw new Error('Selected match does not identify a backend candidate report.')
  return generateCandidateQuestionsApi(runId, candidateId, taskId)
}

async function fetchQuestionsForMatch(match: MatchResult): Promise<CandidateReport> {
  const [runId, candidateId] = match.id.split(':')
  if (!runId || !candidateId) throw new Error('Selected match does not identify a backend candidate report.')
  return fetchCandidateReportApi(runId, candidateId)
}

export function buildQuestionSetFromReport(
  jd: DocumentRecord | null,
  resume: DocumentRecord | null,
  questions: ReportQuestion[] | undefined,
  requestedCount: number,
  match?: MatchResult,
  report?: CandidateReport,
): QuestionSet {
  const jdTitle = String(
    report?.job_profile?.job_title ||
      jd?.parsedContent?.title ||
      jd?.parsedContent?.job_title ||
      jd?.filename.replace(/\.[^.]+$/, '') ||
      match?.jdTitle,
  )
  const candidateName = String(
    report?.candidate_name ||
      resume?.parsedContent?.name ||
      resume?.parsedContent?.candidate_name ||
      resume?.filename.replace(/\.[^.]+$/, '') ||
      match?.candidateName,
  )
  const safeQuestions = Array.isArray(questions) ? questions : []
  const evidenceByChunkId = buildEvidenceIndex(report)
  const selectedQuestions = safeQuestions.slice(0, Math.max(1, Math.min(requestedCount, safeQuestions.length)))
  return {
    id: match ? createQuestionSetId(match.id) : createId('qs'),
    jdId: jd?.id || match?.jdId || '',
    jdTitle,
    resumeId: resume?.id || match?.resumeId || '',
    candidateName,
    questionCount: selectedQuestions.length,
    followUpCount: Array.isArray(report?.ambiguity_followups) ? report.ambiguity_followups.length : 0,
    createdAt: new Date().toISOString(),
    questions: selectedQuestions.map((question) => buildFrontendQuestion(question, evidenceByChunkId, match, report)),
    followUpQuestions: (Array.isArray(report?.ambiguity_followups) ? report.ambiguity_followups : []).map((question) =>
      buildFrontendQuestion(question, evidenceByChunkId, match, report),
    ),
  }
}

function buildFrontendQuestion(
  question: ReportQuestion,
  evidenceByChunkId: Map<string, EvidenceChunk>,
  match?: MatchResult,
  report?: CandidateReport,
) {
      const suggestedFollowUps = Array.isArray(question.suggested_followups) ? question.suggested_followups : []
      return {
        id: createId('q'),
        title: question.question,
        type: question.question_type,
        difficulty: mapDifficulty(question.difficulty),
        focus: Array.isArray(question.assessment_points) ? question.assessment_points : [],
        evidence: resolveQuestionEvidence(question, evidenceByChunkId),
        idealAnswer: question.reference_answer_direction,
        rubric: Array.isArray(question.scoring_rubric) ? question.scoring_rubric : [],
        followUps: suggestedFollowUps.length ? suggestedFollowUps : [match?.conclusion || report?.summary || 'Continue verification.'],
      }
}

function buildEvidenceIndex(report?: CandidateReport): Map<string, EvidenceChunk> {
  const evidenceByChunkId = new Map<string, EvidenceChunk>()
  for (const evaluation of report?.evaluations || []) {
    for (const item of evaluation.evidence || []) {
      evidenceByChunkId.set(item.chunk_id, item)
    }
  }
  return evidenceByChunkId
}

function resolveQuestionEvidence(question: ReportQuestion, evidenceByChunkId: Map<string, EvidenceChunk>) {
  const evidence = Array.isArray(question.evidence) && question.evidence.length
    ? question.evidence
    : (question.evidence_chunk_ids || []).map((chunkId) => evidenceByChunkId.get(chunkId)).filter((item): item is EvidenceChunk => Boolean(item))
  return evidence.map((item) => `${item.filename} p${item.page_number}: ${item.text}`).join('\n')
}

function createQuestionSetId(matchId: string) {
  return `qs_${matchId.replace(/[^a-zA-Z0-9_-]/g, '_')}`
}

function mapDifficulty(value: string): '基础' | '中等' | '深入' {
  if (value === 'easy') return '基础'
  if (value === 'hard') return '深入'
  return '中等'
}
