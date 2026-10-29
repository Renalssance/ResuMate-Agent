import { beforeEach, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useQuestionStore } from './question'
import { getReportForMatch } from './match'
import { fetchAgentRun } from '../api/agentRuns'
import { fetchCandidateReportApi, generateCandidateQuestionsApi } from '../api/runs'
vi.mock('./match', () => ({ getReportForMatch: vi.fn() }))
vi.mock('../api/agentRuns', () => ({ fetchAgentRun: vi.fn() }))
vi.mock('../api/runs', () => ({ fetchCandidateReportApi: vi.fn(), generateCandidateQuestionsApi: vi.fn() }))
beforeEach(() => { setActivePinia(createPinia()); localStorage.clear(); vi.resetAllMocks() })
it('restores the accepted task result even if a newer run replaced the current candidate report', async () => {
 const report = { candidate_name: '示例', evaluations: [], formal_questions: [{ question: '旧任务原题', question_type: 'resume_experience', difficulty: 'easy', assessment_points: [], scoring_rubric: [], evidence_chunk_ids: [], suggested_followups: [] }], ambiguity_followups: [] }
 vi.mocked(fetchAgentRun).mockResolvedValue({ status: 'succeeded', result: report } as any)
 vi.mocked(fetchCandidateReportApi).mockResolvedValue({ ...report, formal_questions: [{ ...report.formal_questions[0], question: '后一次生成的新题' }] } as any)
 const store = useQuestionStore()
 await (store.restoreQuestionSet as any)({ id: 'jd:1', filename: '岗位.txt' }, { id: 'resume:2', filename: '简历.txt' }, 1, { id: '3:4' }, 'accepted-question-run')
 expect(fetchAgentRun).toHaveBeenCalledWith('accepted-question-run')
 expect(fetchCandidateReportApi).not.toHaveBeenCalled()
 expect(store.questionSets[0]?.questions[0]?.title).toBe('旧任务原题')
})

it('loads persisted question history from the cached candidate report without calling a model', () => {
 vi.mocked(getReportForMatch).mockReturnValue({ candidate_name: '历史候选人', job_profile: { job_title: '已保存岗位' }, evaluations: [], formal_questions: [{ question: '历史问题', question_type: 'resume_experience', difficulty: 'easy', assessment_points: [], scoring_rubric: [], evidence_chunk_ids: [], suggested_followups: [] }], ambiguity_followups: [] } as any)
 const store = useQuestionStore()
 store.loadQuestionSets([{ id: '5:6', jdId: 'jd:3', resumeId: 'resume:4' }] as any)
 expect(getReportForMatch).toHaveBeenCalledWith('5:6')
 expect(store.questionSets[0]?.candidateName).toBe('历史候选人')
 expect(store.questionSets[0]?.questions[0]?.title).toBe('历史问题')
 expect(store.questionSets[0]?.questionCount).toBe(1)
})


function pending<T = any>() {
 let resolve!: (value: T) => void, reject!: (error: Error) => void
 const promise = new Promise<T>((success, failure) => { resolve = success; reject = failure })
 return { promise, resolve, reject }
}
const reportFor = (owner: string) => ({ candidate_name: owner, evaluations: [], formal_questions: [{ question: `${owner} question`, question_type: 'resume_experience', difficulty: 'easy', assessment_points: [], scoring_rubric: [], evidence_chunk_ids: [], suggested_followups: [] }], ambiguity_followups: [] })

it.each(['create', 'restore'] as const)('ignores an old account %s result while the new account is still loading', async operation => {
 const first = pending(), second = pending()
 const api = operation === 'create' ? vi.mocked(generateCandidateQuestionsApi) : vi.mocked(fetchAgentRun)
 api.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
 const store = useQuestionStore()
 const start = (owner: string) => operation === 'create'
  ? store.createQuestionSet({ id: `jd:${owner}`, filename: 'job.txt' } as any, { id: `resume:${owner}`, filename: 'resume.txt' } as any, 1, { id: `${owner}:1` } as any)
  : store.restoreQuestionSet({ id: `jd:${owner}`, filename: 'job.txt' } as any, { id: `resume:${owner}`, filename: 'resume.txt' } as any, 1, { id: `${owner}:1` } as any, `accepted-${owner}`)
 const result = (owner: string) => operation === 'create' ? reportFor(owner) : { status: 'succeeded', result: reportFor(owner) }
 localStorage.setItem('accessToken', 'token-A')
 const requestA = start('A')
 localStorage.setItem('accessToken', 'token-B')
 store.loadQuestionSets([])
 const requestB = start('B')
 try {
  first.resolve(result('A')); await requestA
  expect(store.questionSets).toEqual([])
  expect(store.loading).toBe(true)
  expect(store.error).toBe('')
 } finally { second.resolve(result('B')); await requestB }
 expect(store.questionSets.map(set => set.candidateName)).toEqual(['B'])
 expect(store.loading).toBe(false)
})

it.each(['create', 'restore'] as const)('does not replace the new account error with a late %s error', async operation => {
 const first = pending(), second = pending()
 const api = operation === 'create' ? vi.mocked(generateCandidateQuestionsApi) : vi.mocked(fetchAgentRun)
 api.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
 const store = useQuestionStore()
 const start = (owner: string) => operation === 'create'
  ? store.createQuestionSet({ id: 'jd:1' } as any, { id: 'resume:2' } as any, 1, { id: '3:4' } as any)
  : store.restoreQuestionSet({ id: 'jd:1' } as any, { id: 'resume:2' } as any, 1, { id: '3:4' } as any, `accepted-${owner}`)
 localStorage.setItem('accessToken', 'token-A')
 const requestA = start('A')
 localStorage.setItem('accessToken', 'token-B')
 store.loadQuestionSets([])
 const requestB = start('B')
 second.reject(new Error('B request failed'))
 await expect(requestB).rejects.toThrow('B request failed')
 first.reject(new Error('A request failed'))
 await expect(requestA).rejects.toThrow('A request failed')
 expect(store.error).toBe('B request failed')
 expect(store.loading).toBe(false)
 expect(store.questionSets).toEqual([])
})
