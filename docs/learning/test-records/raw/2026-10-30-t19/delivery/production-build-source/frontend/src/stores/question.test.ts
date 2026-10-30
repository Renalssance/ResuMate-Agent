import { buildQuestionSetFromReport } from './question'
import type { CandidateReport } from '../types/run'

function assert(condition: unknown, message: string) {
  if (!condition) throw new Error(message)
}

const report = {
  candidate_name: 'Candidate',
  summary: 'Generated report summary',
  evaluations: [
    {
      evidence: [
        {
          chunk_id: 'chunk-1',
          filename: 'resume.pdf',
          page_number: 2,
          section: 'Projects',
          text: 'Built an AI workflow.',
          score: 0.9,
        },
      ],
    },
  ],
  formal_questions: [
    {
      question: 'Describe the AI workflow.',
      question_type: 'resume_experience',
      difficulty: 'medium',
      assessment_points: ['workflow depth'],
      related_criteria: ['criterion_01'],
      evidence_chunk_ids: ['chunk-1'],
      reference_answer_direction: 'Look for concrete implementation details.',
      scoring_rubric: ['1 low', '3 medium', '5 high'],
      suggested_followups: ['What was hardest?'],
    },
  ],
  ambiguity_followups: [
    {
      question: 'Clarify the AI workflow ownership.',
      question_type: 'gap_validation',
      difficulty: 'medium',
      assessment_points: ['ownership clarity'],
      related_criteria: ['criterion_01'],
      evidence_chunk_ids: ['chunk-1'],
      reference_answer_direction: 'Look for the candidate role and boundaries.',
      scoring_rubric: ['1 vague', '3 clear', '5 specific'],
      suggested_followups: ['Who reviewed the result?'],
    },
  ],
} as unknown as CandidateReport

const questionSet = buildQuestionSetFromReport(null, null, report.formal_questions, 1, undefined, report)

assert(questionSet.questions.length === 1, 'should build one frontend question')
assert(questionSet.questions[0].evidence.includes('resume.pdf p2: Built an AI workflow.'), 'should hydrate evidence from evidence_chunk_ids')
assert(questionSet.questions[0].followUps[0] === 'What was hardest?', 'should preserve suggested follow-ups')
assert(questionSet.followUpQuestions.length === 1, 'should keep ambiguity follow-ups separate from formal questions')
assert(questionSet.followUpQuestions[0].title === 'Clarify the AI workflow ownership.', 'should expose ambiguity follow-ups on the question set')
