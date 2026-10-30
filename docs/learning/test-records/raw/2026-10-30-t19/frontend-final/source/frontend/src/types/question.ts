export interface InterviewQuestion {
  id: string
  title: string
  type: string
  difficulty: string
  focus: string[]
  evidence: string
  idealAnswer: string
  rubric: string[]
  followUps: string[]
}

export interface QuestionSet {
  id: string
  jdId: string
  jdTitle: string
  resumeId: string
  candidateName: string
  questionCount: number
  followUpCount: number
  createdAt: string
  questions: InterviewQuestion[]
  followUpQuestions: InterviewQuestion[]
}
