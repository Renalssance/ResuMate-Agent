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

const view = readSource('views/ApplicationsView.vue')
const css = readSource('styles/main.css')
const chart = readSource('utils/applicationChart.ts')

assert(!view.includes('待推进 / 放弃'), 'total application metric should not show the other-status label')
assert(!chart.includes('待推进 / 放弃'), 'old other-status copy should be removed from application chart source')
assert(view.includes('applicationStatusFilterOptions'), 'application view should render category status filters')
assert(view.includes('applicationMatchesStatusFilter'), 'application view should filter by category groups')
assert(
  css.includes('.application-metric::after') && css.includes('content: none;'),
  'application metric decoration should be removed through the existing metric selector',
)
