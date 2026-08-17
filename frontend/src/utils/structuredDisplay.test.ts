// @ts-expect-error Node's strip-types runner imports the TypeScript source directly.
const { formatStructuredEntries } = await import('./structuredDisplay.ts')

export {}

function assert(condition: unknown, message: string) {
  if (!condition) throw new Error(message)
}

const entries = formatStructuredEntries({
  candidate_name: '朱皆霖',
  contact: {
    手机: '159 5141 9875',
    email: 'grandZJL@outlook.com',
    location: '上海',
  },
  education: [
    {
      school: '上海科技大学',
      degree: '学术型硕士(推免)',
      courses: ['深度学习', '无线通信'],
    },
  ],
})

assert(entries[0].label === '姓名', 'candidate_name should use a readable label')
assert(entries[0].value === '朱皆霖', 'plain values should stay plain text')
assert(entries[1].children[0].label === '手机', 'object values should become label/value children')
assert(entries[1].children[1].value === 'grandZJL@outlook.com', 'object child values should stay readable')
assert(entries[2].groups[0].children[0].label === '学校', 'array objects should render as grouped child rows')
assert(entries[2].groups[0].children[2].value === '深度学习、无线通信', 'nested string arrays should join cleanly')
const visibleText = [
  ...entries.map((entry: any) => entry.value),
  ...entries.flatMap((entry: any) => entry.children.map((child: any) => child.value)),
  ...entries.flatMap((entry: any) => entry.groups.flatMap((group: any) => [group.value, ...group.children.map((child: any) => child.value)])),
].join(' ')
assert(!visibleText.includes('{"'), 'formatted entries should not expose raw JSON text')
