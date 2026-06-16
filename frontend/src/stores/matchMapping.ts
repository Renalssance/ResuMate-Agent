import type { MatchResult } from '../types/match'
import type { CandidateReport, CandidateSummary, EvidenceChunk } from '../types/run'

export function reportToMatch(runId: string, candidate: CandidateSummary, report: CandidateReport): MatchResult {
  const id = `${runId}:${candidate.candidate_id}`
  const jobProfile = report.job_profile
  const evaluations = Array.isArray(report.evaluations) ? report.evaluations : []
  const evidence = evaluations.flatMap((item) => formatEvaluationEvidence(item.evidence))
  const warnings = [...(Array.isArray(report.warnings) ? report.warnings : [])]
  if (!evidence.length && !warnings.length) {
    warnings.push('未找到可展示的证据引用，匹配结果仍已保存。')
  }
  return {
    id,
    jdId: runId,
    jdTitle: jobProfile?.job_title || extractJobTitle(report.summary),
    resumeId: String(candidate.candidate_id),
    candidateName: candidate.candidate_name,
    score: candidate.total_score,
    conclusion: recommendationText(candidate.recommendation),
    strengths: Array.isArray(candidate.top_strengths) ? candidate.top_strengths : [],
    gaps: evaluations.flatMap((item) => item.missing_evidence || []).slice(0, 3),
    risks: evaluations.map((item) => item.risk).filter(Boolean).slice(0, 3),
    warnings: [...new Set(warnings)],
    summary: report.summary,
    criteria: evaluations.map((item) => ({
      name: item.name,
      weight: item.weight,
      score: item.score,
      reason: item.reason,
    })),
    evidence,
    agentContent: report.summary,
    logs: [
      'Documents indexed in Milvus',
      'Evidence retrieved per JD criterion',
      'LLM evaluated criterion-level match',
      'Python calculated total score',
    ],
    createdAt: new Date().toISOString(),
  }
}

function formatEvaluationEvidence(evidence: EvidenceChunk[] | undefined) {
  return (Array.isArray(evidence) ? evidence : []).map(
    (item) => `${item.filename} p${item.page_number} ${item.section}: ${item.text}`,
  )
}

function extractJobTitle(summary: string) {
  return summary.split(' matched ')[1]?.split(' with score ')[0] || 'JD'
}

function recommendationText(value: string) {
  const map: Record<string, string> = {
    strong_recommend: 'Strong recommend',
    recommend: 'Recommend',
    hold: 'Hold',
    reject: 'Reject',
  }
  return map[value] || value
}
