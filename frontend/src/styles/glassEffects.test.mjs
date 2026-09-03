import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const srcRoot = resolve(here, '..')

function readSource(path) {
  return readFileSync(resolve(srcRoot, path), 'utf8')
}

function assert(condition, message) {
  if (!condition) throw new Error(message)
}

const css = readSource('styles/main.css')
const viewFiles = [
  'views/DocumentsView.vue',
  'views/MatchingView.vue',
  'views/ApplicationsView.vue',
  'views/ProfileFieldsView.vue',
  'views/SettingsView.vue',
  'views/QuestionsView.vue',
]
const views = viewFiles.map((file) => ({ file, source: readSource(file) }))
const reusableClasses = ['glass-surface', 'glass-surface-strong', 'glass-action', 'glass-live']
const combinedSelectors = [
  '.metric-card.glass-surface',
  '.result-card.glass-surface-strong',
  '.coverage-card.glass-surface-strong',
  '.settings-model-hero.glass-surface-strong',
  '.workflow-action-panel.glass-live',
  '.question-flow-grid.glass-live',
  '.schedule-today-panel.glass-live',
  '.button-secondary.glass-action',
]
const frostedGlassTokens = [
  'border-radius: 18px',
  'backdrop-filter: blur(24px) saturate(185%) contrast(106%) brightness(108%)',
  'background: rgba(255, 255, 255, 0.3)',
  'background: rgba(255, 255, 255, 0.38)',
  'background: rgba(240, 249, 245, 0.28)',
  'background: rgba(255, 255, 255, 0.24)',
  'border-color: rgba(255, 255, 255, 0.82)',
  'inset 0 1px rgba(255, 255, 255, 0.96)',
  'inset 0 0 22px rgba(255, 255, 255, 0.22)',
  'overflow: hidden',
  'isolation: isolate',
]
const fluidBackgroundTokens = [
  '.fluid-bg',
  'position: fixed',
  'pointer-events: none',
  'background: #edf5e2',
  '.fluid-bg canvas',
  'width: 100% !important',
  'height: 100% !important',
]
const forbiddenGlassTokens = [
  'background-blend-mode: screen, normal, normal',
  'linear-gradient(145deg, rgba(255, 255, 255, 0.86)',
  'linear-gradient(145deg, rgba(255, 255, 255, 0.9)',
  'linear-gradient(145deg, rgba(246, 251, 248, 0.78)',
  'linear-gradient(145deg, rgba(255, 255, 255, 0.74)',
]

for (const className of reusableClasses) {
  assert(css.includes(`.${className}`), `${className} should be defined as a reusable glass class`)
}

const totalGlassUsages = views.reduce((count, view) => (
  count + reusableClasses.filter((className) => view.source.includes(className)).length
), 0)

assert(totalGlassUsages >= 6, 'glass classes should be reused across selected cards and actions')

for (const className of reusableClasses) {
  const usedInFiles = views.filter((view) => view.source.includes(className)).map((view) => view.file)
  assert(usedInFiles.length >= 2, `${className} should be reused in multiple view components`)
}

for (const selector of combinedSelectors) {
  assert(css.includes(selector), `${selector} should preserve glass styling against component-level CSS`)
}

for (const token of frostedGlassTokens) {
  assert(css.includes(token), `frosted glass styling should include ${token}`)
}

for (const token of fluidBackgroundTokens) {
  assert(css.includes(token), `page background should include fluid background token: ${token}`)
}

for (const token of forbiddenGlassTokens) {
  assert(!css.includes(token), `glass styling should avoid card/button gradients: ${token}`)
}
