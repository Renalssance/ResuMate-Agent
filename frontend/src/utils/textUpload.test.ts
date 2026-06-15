// @ts-expect-error Node's strip-types runner imports the TypeScript source directly.
const { createTextUploadFile } = await import('./textUpload.ts')

export {}

function assert(condition: unknown, message: string) {
  if (!condition) throw new Error(message)
}

const fixedNow = () => new Date('2026-06-14T12:34:56.000Z')

const jdFile = createTextUploadFile('jd', '  Senior backend engineer\nBuild APIs.  ', fixedNow)
assert(jdFile.name === 'jd-text-20260614-123456.txt', 'JD text upload should use a stable txt filename')
assert(jdFile.type === 'text/plain;charset=utf-8', 'text upload file should be UTF-8 plain text')
assert(await jdFile.text() === 'Senior backend engineer\nBuild APIs.', 'text upload should trim surrounding whitespace')

const resumeFile = createTextUploadFile('resume', 'Candidate resume text', fixedNow)
assert(resumeFile.name === 'resume-text-20260614-123456.txt', 'resume text upload should include document type')

let emptyRejected = false
try {
  createTextUploadFile('jd', '   ', fixedNow)
} catch {
  emptyRejected = true
}
assert(emptyRejected, 'empty text upload should be rejected')
