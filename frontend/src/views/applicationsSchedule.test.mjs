import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const view = readFileSync(resolve(root, 'views/ApplicationsView.vue'), 'utf8')

function assert(condition, message) {
  if (!condition) throw new Error(message)
}

assert(
  view.includes('activeScheduleItems'),
  'applications view should render active schedules separately from completed schedules',
)
assert(
  view.includes('completedScheduleItems'),
  'applications view should keep completed schedules in their own list',
)
assert(
  view.includes('showCompletedSchedules'),
  'applications view should keep completed schedules collapsed by default',
)
assert(
  view.includes('已完成日程'),
  'applications view should expose a completed schedules toggle label',
)
