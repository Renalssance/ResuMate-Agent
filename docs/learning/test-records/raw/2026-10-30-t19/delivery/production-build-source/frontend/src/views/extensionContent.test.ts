// @ts-expect-error Node's strip-types runner imports the TypeScript source directly.
const { extensionDownload, installSteps, usageSteps, safetyNotes } = await import('./extensionContent.ts')

export {}

function assert(condition: unknown, message: string) {
  if (!condition) throw new Error(message)
}

assert(extensionDownload.href === '/downloads/resumate-autofill-extension.zip', 'extension download should point to the packaged zip')
assert(installSteps.some((step: string) => step.includes('chrome://extensions')), 'install steps should explain Chrome/Edge extension loading')
assert(usageSteps.some((step: string) => step.includes('扫描页面')), 'usage steps should include scanning the application page')
assert(safetyNotes.some((note: string) => note.includes('不会自动提交')), 'safety notes should state that applications are never submitted automatically')
