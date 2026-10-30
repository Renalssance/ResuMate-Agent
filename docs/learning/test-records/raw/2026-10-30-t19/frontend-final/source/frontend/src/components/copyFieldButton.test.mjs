import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { parse, compileScript } from '@vue/compiler-sfc'
import ts from 'typescript'
import { createRenderer, h, nextTick, reactive } from 'vue'

const { descriptor } = parse(readFileSync(new URL('./CopyFieldButton.vue', import.meta.url), 'utf8'))
const script = compileScript(descriptor, { id: 'copy-field-test', inlineTemplate: true })
const source = ts.transpileModule(script.content, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText
  .replace(/from (['"])(vue|@lucide\/vue)\1/g, (_, quote, name) => `from ${JSON.stringify(import.meta.resolve(name))}`)
const { default: CopyFieldButton } = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`)

// Render the actual component with a small host; only the OS clipboard is replaced.
const renderer = createRenderer({
  createElement: (tag) => ({ tag, props: {}, children: [] }),
  createText: (text) => ({ text }),
  createComment: (text) => ({ text }),
  setText: (node, text) => { node.text = text },
  setElementText: (node, text) => { node.text = text },
  patchProp: (node, key, previous, value) => { node.props[key] = value },
  insert(node, parent, anchor) {
    if (node.parent) node.parent.children.splice(node.parent.children.indexOf(node), 1)
    node.parent = parent
    const index = anchor ? parent.children.indexOf(anchor) : -1
    if (index < 0) parent.children.push(node)
    else parent.children.splice(index, 0, node)
  },
  remove(node) { node.parent.children.splice(node.parent.children.indexOf(node), 1) },
  parentNode: (node) => node.parent,
  nextSibling: (node) => node.parent?.children[node.parent.children.indexOf(node) + 1] || null,
})
let copied = ''
Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: async (text) => { copied = text } } })
const props = reactive({ value: ['论文一', '论文二'], label: '论文' })
const root = { children: [] }
renderer.createApp({ render: () => h(CopyFieldButton, props) }).mount(root)
const button = root.children.find(node => node.tag === 'button')
assert.equal(button.props.disabled, false)
assert.equal(button.props['aria-label'], '复制论文')
assert.equal(button.text || '', '', 'copy controls must show an icon without visible text')
assert.match(button.children.find((node) => node.tag === 'svg')?.props.class || '', /lucide-copy/, 'copy control must render a library icon')
await button.props.onClick({ preventDefault() {} })
await nextTick()
assert.equal(copied, '论文一\n论文二', 'copy must use the full current field value')
assert.equal(button.props['aria-label'], '已复制论文')
assert.match(button.children.find((node) => node.tag === 'svg')?.props.class || '', /lucide-copy-check/, 'successful copying must display a check on the copy icon')

props.value = ['新的论文']
await nextTick()
assert.equal(button.props['aria-label'], '复制论文', 'changing the field must clear old copy feedback')
navigator.clipboard.writeText = async () => { throw new Error('permission denied') }
await button.props.onClick({ preventDefault() {} })
await nextTick()
assert.equal(button.props['aria-label'], '复制论文失败', 'clipboard errors must not report success')
assert.match(button.children.find((node) => node.tag === 'svg')?.props.class || '', /lucide-copy-x/)

assert.match(root.children.filter(node => node.tag === 'span').map(node => node.text || '').join(''), /手动选中/, 'copy failure must include visible manual-copy guidance')

props.value = []
await nextTick()
assert.equal(button.props.disabled, true, 'empty fields must not offer a misleading copy action')
console.log('Copy field checks passed.')
