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

const layout = readSource('components/AppLayout.vue')
const css = readSource('styles/main.css')

assert(
  layout.includes('import { AestheticFluidBg } from \'color4bg\''),
  'app layout should use color4bg aesthetic fluid background',
)
assert(
  layout.includes('id="box"') && layout.includes('fluid-bg'),
  'app layout should expose a stable full-screen background mount',
)
assert(
  layout.includes('["#1D4600", "#4F9900", "#82C23A", "#D7E356", "#A5C940", "#1D4600"]'),
  'fluid background should use the selected green palette',
)
assert(
  layout.includes('loop: !prefersReducedMotion'),
  'fluid background should stop looping for reduced-motion users',
)
assert(
  layout.includes("colorbg.update('scale', 0.03)"),
  'fluid background should set the selected blur scale',
)
assert(
  layout.includes('isGlassTheme ? \'is-glass-theme\' : \'is-simple-theme\''),
  'app layout should default through a root appearance class',
)
assert(
  layout.includes('role="switch"') && layout.includes(':aria-checked="isGlassTheme"') && layout.includes('玻璃效果'),
  'topbar should expose an accessible glass effect switch',
)
assert(
  layout.includes('localStorage.getItem(APPEARANCE_STORAGE_KEY)')
    && layout.includes('localStorage.setItem(APPEARANCE_STORAGE_KEY'),
  'appearance switch should persist the user choice in localStorage',
)
assert(
  css.includes('.fluid-bg') && css.includes('position: fixed') && css.includes('pointer-events: none'),
  'fluid background should be fixed behind the app without blocking interaction',
)
assert(
  css.includes('.is-simple-theme .fluid-bg') && css.includes('display: none'),
  'simple theme should hide the animated fluid background',
)
