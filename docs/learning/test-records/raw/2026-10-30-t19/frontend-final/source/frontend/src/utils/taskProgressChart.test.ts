// @ts-expect-error Node's strip-types runner imports the TypeScript source directly.
const { buildProgressSegments } = await import('./taskProgressChart.ts')

export {}

function assert(condition: unknown, message: string) {
  if (!condition) throw new Error(message)
}

const segments = buildProgressSegments([
  { key: 'upload', label: '上传', status: 'success', progress: 20 },
  { key: 'parse', label: '解析', status: 'running', progress: 45 },
  { key: 'save', label: '保存', status: 'pending', progress: 0 },
  { key: 'index', label: '入库', status: 'failed', progress: 10 },
])

assert(
  segments.map((item: { fillPercent: number }) => item.fillPercent).join(',') === '100,45,0,100',
  'progress segments should fill by step state and running progress',
)
assert(
  segments.map((item: { status: string }) => item.status).join(',') === 'success,running,pending,failed',
  'progress segments should keep each step status for styling',
)
assert(segments[1].title === '解析 · 45%', 'running progress segment should expose a readable title')

const clamped = buildProgressSegments([
  { key: 'low', label: '过低', status: 'running', progress: -10 },
  { key: 'high', label: '过高', status: 'running', progress: 160 },
])

assert(
  clamped.map((item: { fillPercent: number }) => item.fillPercent).join(',') === '0,100',
  'running segment fill should stay within 0-100',
)
