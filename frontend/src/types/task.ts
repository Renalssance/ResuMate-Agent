export type TaskStatus = 'pending' | 'running' | 'success' | 'failed'

export interface ProgressStep {
  key: string
  label: string
  status: TaskStatus
  progress: number
  message?: string
}

export interface SseProgressEvent {
  taskId: string
  documentId?: string
  filename?: string
  stage: string
  status: TaskStatus
  progress: number
  overallProgress?: number
  stageProgress?: number
  current?: number
  total?: number
  message: string
  data?: Record<string, unknown>
}

export interface StepTemplate {
  key: string
  label: string
}

export const PARSE_STEPS: StepTemplate[] = [
  { key: 'upload_client', label: '文件上传' },
  { key: 'server_save', label: '服务端保存' },
  { key: 'extract', label: '文本提取' },
  { key: 'llm_analyze', label: 'LLM 结构化分析' },
  { key: 'embedding', label: '向量生成' },
  { key: 'milvus_save', label: '向量库入库' },
  { key: 'local_save', label: '本地保存' },
]

export const MATCH_STEPS: StepTemplate[] = [
  { key: 'load_jd', label: '加载结构化 JD' },
  { key: 'load_resume', label: '加载结构化简历' },
  { key: 'milvus_search', label: 'Milvus 检索相关证据' },
  { key: 'llm_match', label: 'LLM 逐项匹配分析' },
  { key: 'score', label: 'Python 计算总分' },
  { key: 'vectorize', label: '匹配结果向量化' },
  { key: 'milvus_save', label: 'Milvus 入库' },
]

export const QUESTION_STEPS: StepTemplate[] = [
  { key: 'load_context', label: '加载 JD 与简历' },
  { key: 'retrieve_evidence', label: '检索候选人证据' },
  { key: 'analyze_gaps', label: '分析岗位重点和能力缺口' },
  { key: 'generate_questions', label: 'LLM 生成试题' },
  { key: 'rubric', label: '生成评分标准' },
  { key: 'save', label: '结果入库' },
]
