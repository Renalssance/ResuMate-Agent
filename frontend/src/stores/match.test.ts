// @ts-expect-error Node's strip-types runner imports the TypeScript source directly.
const { reportToMatch } = await import('./matchMapping.ts')

export {}

function assert(condition: unknown, message: string) {
  if (!condition) throw new Error(message)
}

const report = {
  candidate_name: 'Ada',
  summary: 'Ada matched Backend Engineer with score 60 and recommendation hold.',
  job_profile: {
    job_title: 'Backend Engineer',
  },
  evaluations: [
    {
      criterion_id: 'c1',
      name: 'Python',
      weight: 100,
      score: 0,
      status: 'no_evidence',
      reason: 'No usable evidence.',
      evidence_chunk_ids: [],
      missing_evidence: ['direct project evidence'],
      risk: '',
    },
  ],
  warnings: ['未找到可用于引用的简历证据，匹配结果已保存，但证据展示和题目依据可能不完整。'],
}

const candidate = {
  candidate_id: 2,
  candidate_name: 'Ada',
  filename: 'ada.pdf',
  total_score: 60,
  recommendation: 'hold',
  top_strengths: [],
}

const match = reportToMatch('1', candidate, report as any)

assert(match.evidence.length === 0, 'missing evaluation evidence should be treated as an empty evidence list')
assert(match.warnings.length === 1, 'backend warnings should be exposed on the frontend match')
