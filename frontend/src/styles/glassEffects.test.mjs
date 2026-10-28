import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import postcss from 'postcss'

// v1.1 replaces nested glass cards and translucent refresh buttons with solid content.
// Keep structural material/motion contracts here; dimensions and rendering are checked in Chrome.
const css = readFileSync(new URL('./main.css', import.meta.url), 'utf8')
const root = postcss.parse(css)
root.walkRules(rule => {
  assert.ok(rule.selector.trim(), 'every CSS rule needs a selector')
  assert.ok(!/\.glass-(surface|live|action)/.test(rule.selector), 'obsolete content glass overrides must not return')
  rule.walkDecls(/^transition/, declaration => {
    assert.ok(!/\ball\b/.test(declaration.value), 'transitions must identify the properties they animate')
    if (rule.selector === '*') assert.ok(rule.parent.type === 'atrule', 'ordinary elements must not inherit global transitions')
  })
  rule.walkDecls(/backdrop-filter$/, declaration => {
    if (declaration.value === 'none') return
    for (const selector of rule.selectors) {
      assert.match(selector, /\.(app-sidebar|topbar|detail-drawer)/, 'glass belongs to navigation or overlays')
    }
  })
})
for (const key of ['.fluid-bg', '.fluid-bg canvas', '.is-simple-theme .fluid-bg']) {
  assert.ok(css.includes(key), `preserve the background mounting/visibility contract: ${key}`)
}
assert.ok(!css.includes('z-index: -1'), 'background must remain in the app stacking context')
console.log('v1.1 material and motion structure passed.')
