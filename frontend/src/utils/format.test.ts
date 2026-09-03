// @ts-expect-error Node's strip-types runner imports the TypeScript source directly.
const { formatResumeLabel } = await import('./format.ts')

export {}

function assert(condition: unknown, message: string) {
  if (!condition) throw new Error(message)
}

assert(
  formatResumeLabel({ filename: 'resume-ai-test.pdf', parsedContent: { name: '朱皆霖' } }) === '朱皆霖（resume-ai-test.pdf）',
  'resume label should include both candidate name and resume filename',
)

assert(
  formatResumeLabel({ filename: 'resume-ai-test.pdf', parsedContent: {} }) === 'resume-ai-test.pdf',
  'resume label should fall back to filename when candidate name is missing',
)
