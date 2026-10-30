import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(path) {
  return readFileSync(resolve(root, path), 'utf8')
}

function assert(condition, message) {
  if (!condition) throw new Error(message)
}

const api = readSource('api/applications.ts')
const store = readSource('stores/application.ts')
const view = readSource('views/ApplicationsView.vue')

assert(
  api.includes('completeApplicationScheduleApi'),
  'applications API should expose schedule completion',
)
assert(
  api.includes('/schedules/${scheduleId}/complete'),
  'schedule completion API should call the complete endpoint',
)
assert(
  store.includes('completeSchedule'),
  'application store should expose schedule completion',
)
assert(
  view.includes('@click="completeSchedule(schedule)"'),
  'applications view should render a schedule completion button',
)
