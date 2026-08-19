// @ts-expect-error Node's strip-types runner imports the TypeScript source directly.
const { buildCriterionChartRows, clampScorePercent } = await import('./matchChart.ts')

export {}

function assert(condition: unknown, message: string) {
  if (!condition) throw new Error(message)
}

assert(clampScorePercent(120) === 100, 'match score percent should cap at 100')
assert(clampScorePercent(-5) === 0, 'match score percent should floor at 0')
assert(clampScorePercent(68.4) === 68, 'match score percent should round display values')

const rows = buildCriterionChartRows([
  { name: 'Evidence', weight: 35, score: 2, reason: 'Thin project evidence.' },
  { name: 'Architecture', weight: 40, score: 5, reason: 'Strong system design match.' },
  { name: 'Culture', weight: 25, score: 4, reason: 'Good collaboration history.' },
])

assert(
  rows.map((item: { name: string }) => item.name).join(',') === 'Architecture,Culture,Evidence',
  'criteria rows should sort by weighted contribution',
)
assert(rows[1].scorePercent === 80, 'criterion score should map from the 0-5 scale to percent width')
assert(rows[2].scorePercent === 40, 'low criterion score should keep proportional width')
assert(rows[0].contribution === 40, 'weighted contribution should match backend total-score formula')
