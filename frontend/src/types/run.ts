export interface EvidenceChunk {
  chunk_id: string
  filename: string
  page_number: number
  section: string
  text: string
  score: number
}

export interface CandidateSummary {
  candidate_id: number
  candidate_name: string
  filename: string
  total_score: number
  recommendation: string
  top_strengths: string[]
}

export interface RunSummary {
  run_id: number
  job_title: string
  candidates: CandidateSummary[]
}

export interface CriterionEvaluation {
  criterion_id: string
  name: string
  weight: number
  score: number
  status: string
  reason: string
  evidence?: EvidenceChunk[]
  missing_evidence: string[]
  risk: string
}

export interface ResumeProfile {
  candidate_name: string
  contact: Record<string, string>
  education: unknown[]
  work_experience: unknown[]
  projects: unknown[]
  skills: string[]
  achievements: string[]
  ambiguities: string[]
  source_refs: unknown[]
}

export interface InterviewQuestion {
  question: string
  question_type: string
  difficulty: string
  assessment_points: string[]
  related_criteria: string[]
  evidence?: EvidenceChunk[]
  evidence_chunk_ids?: string[]
  reference_answer_direction: string
  scoring_rubric: string[]
  suggested_followups?: string[]
}

export interface CandidateReport {
  run_id: number
  candidate_id: number
  candidate_name: string
  filename: string
  job_profile?: {
    job_title: string
    summary: string
    responsibilities: string[]
    criteria: unknown[]
    interview_focus: string[]
  }
  resume_profile: ResumeProfile
  evaluations: CriterionEvaluation[]
  total_score: number
  recommendation: string
  top_strengths: string[]
  warnings?: string[]
  summary: string
  formal_questions: InterviewQuestion[]
  ambiguity_followups: InterviewQuestion[]
}

export interface EvidenceSearchResponse {
  run_id: number
  candidate_id: number
  results: EvidenceChunk[]
}
