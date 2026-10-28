// @ts-expect-error Node's strip-types runner imports the TypeScript source directly.
const { groupApplicationsByCompany } = await import('./applicationGrouping.ts')

export {}

function assert(condition: unknown, message: string) {
  if (!condition) throw new Error(message)
}

const applications = [
  { id: 3, company: '字节跳动', position: '后端开发', schedules: [{ id: 31 }], statusEvents: [{ id: 301 }] },
  { id: 2, company: '腾讯', position: '前端开发', schedules: [{ id: 21 }], statusEvents: [{ id: 201 }] },
  { id: 1, company: '字节跳动', position: '算法工程师', schedules: [{ id: 11 }], statusEvents: [{ id: 101 }] },
]

const groups = groupApplicationsByCompany(applications)

assert(groups.length === 2, 'applications from the same company should be shown in one group')
assert(
  groups[0].company === '字节跳动' && groups[0].applications.map((application) => application.id).join(',') === '3,1',
  'a company group should retain every position in its original order',
)
assert(
  groups[0].applications[0].schedules[0].id === 31
    && groups[0].applications[1].statusEvents[0].id === 101
    && groups[0].applications[0] !== groups[0].applications[1],
  'grouping should keep each position and its schedule and timeline records independent',
)
assert(
  groups[1].company === '腾讯' && groups[1].applications[0].id === 2,
  'applications from another company should remain in a separate group',
)

const prioritized = groupApplicationsByCompany([
  ...applications,
  { ...applications[0], id: 4, company: '小米' },
  { ...applications[0], id: 5, company: '网易' },
], new Set([2, 4]))
assert(
  prioritized.map((group) => group.company).join(',') === '腾讯,小米,字节跳动,网易',
  'companies with unfinished schedules should appear first while retaining order within each section',
)
assert(
  prioritized[2].applications.map((application) => application.id).join(',') === '3,1',
  'prioritizing companies must retain every position without changing its order',
)
